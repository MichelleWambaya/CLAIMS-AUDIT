import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import ClaimRow, Flag, FlagReview, FlagOverride, RuleConfigRow, User
from auth.security import get_current_user, require_admin
from rules import (
    RuleConfig, DEFAULT_CONFIG, run_all_rules,
)

router = APIRouter(prefix="/sessions/{session_id}/flags", tags=["flags"])


def _load_config(db: Session, session_id: str) -> RuleConfig:
    row = db.query(RuleConfigRow).filter(RuleConfigRow.audit_session_id == session_id).first()
    if not row:
        return DEFAULT_CONFIG
    return RuleConfig(**row.config_json)


def _row_to_dict(r: ClaimRow, index: int) -> dict:
    return {
        "row_index": r.id,
        "member_id": r.member_id,
        "membership_number": r.member_id,
        "policy_number": r.policy_number,
        "payer": r.payer,
        "category": r.category,
        "amount": float(r.amount) if r.amount is not None else None,
        "diagnosis_name": r.diagnosis_name,
        "diagnosis_type": r.diagnosis_type,
        "product_name": r.product_name,
        "visit_date": r.visit_date,
        "item_status": r.item_status,
        "invoice_number": r.invoice_number,
        "claim_date": r.claim_date,
        "_has_item_status_column": r.has_item_status_column,
    }


@router.post("/recompute")
def recompute_flags(session_id: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """
    Runs the full rule engine (rules/) over this session's merged
    claim_rows and replaces the stored flags. In production this runs as a
    background job for large sessions (§7: "Exports/flag computation...
    as background jobs") — synchronous here for clarity.
    """
    config = _load_config(db, session_id)
    all_rows = db.query(ClaimRow).filter(ClaimRow.audit_session_id == session_id).all()

    item_rows = [_row_to_dict(r, i) for i, r in enumerate(all_rows) if r.product_name and r.visit_date]
    claim_rows = [_row_to_dict(r, i) for i, r in enumerate(all_rows)]

    results = run_all_rules(item_rows, claim_rows, config)

    db.query(Flag).filter(Flag.audit_session_id == session_id).delete()

    count = 0
    for flag_type_key, flag_list in results.items():
        flag_type = {
            "item_level_duplicates": "item_duplicate",
            "claim_level_duplicates": "claim_duplicate",
            "non_payable": "non_payable",
            "pricing_anomalies": "pricing_anomaly",
            "invalid_member_policy": "invalid_member_policy",
            "diagnosis_gaps": "diagnosis_gap",
        }[flag_type_key]

        for f in flag_list:
            detail = {k: (str(v) if isinstance(v, date) else v) for k, v in vars(f).items()}
            db.add(Flag(
                audit_session_id=session_id,
                flag_type=flag_type,
                group_id=detail.get("group_id"),
                detail=detail,
            ))
            count += 1

    db.commit()
    return {"flags_computed": count}


@router.get("")
def list_flags(session_id: str, flag_type: Optional[str] = Query(None),
               limit: int = Query(100, le=1000), offset: int = Query(0),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Flag).filter(Flag.audit_session_id == session_id)
    if flag_type:
        q = q.filter(Flag.flag_type == flag_type)
    total = q.count()
    rows = q.order_by(Flag.id).offset(offset).limit(limit).all()
    return {
        "total": total,
        "flags": [
            {"id": f.id, "flag_type": f.flag_type, "group_id": f.group_id, "detail": f.detail}
            for f in rows
        ],
    }


class ReviewRequest(BaseModel):
    status: str  # confirmed | false_positive | needs_follow_up
    note: Optional[str] = None


@router.post("/{flag_id}/review")
def review_flag(session_id: str, flag_id: int, body: ReviewRequest,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.status not in ("confirmed", "false_positive", "needs_follow_up"):
        raise HTTPException(status_code=400, detail="Invalid status")
    review = FlagReview(flag_id=flag_id, reviewed_by=user.id, status=body.status, note=body.note)
    db.add(review)
    db.commit()
    return {"id": review.id, "status": review.status}


class OverrideRequest(BaseModel):
    justification: str


@router.post("/{flag_id}/override")
def override_flag(session_id: str, flag_id: int, body: OverrideRequest,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    §5.2's exception path for non-payable flags — e.g. a supplement
    prescribed for a diagnosed deficiency. Tracked separately from the
    keyword library so overrides don't require editing detection rules,
    and override usage stays reportable (false-positive-rate visibility).
    """
    override = FlagOverride(flag_id=flag_id, approved_by=user.id, justification=body.justification)
    db.add(override)
    db.commit()
    return {"id": override.id}


class RuleConfigUpdate(BaseModel):
    config: dict


@router.get("/config")
def get_rule_config(session_id: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    row = db.query(RuleConfigRow).filter(RuleConfigRow.audit_session_id == session_id).first()
    if row:
        return {"config": row.config_json}
    # No override saved yet — return the code defaults so the admin UI
    # has something to show and edit from.
    from dataclasses import asdict
    return {"config": asdict(DEFAULT_CONFIG)}


@router.put("/config", dependencies=[Depends(require_admin)])
def update_rule_config(session_id: str, body: RuleConfigUpdate, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Admin-only, per §8: thresholds are configurable without a deploy,
    with change history."""
    existing = db.query(RuleConfigRow).filter(RuleConfigRow.audit_session_id == session_id).first()
    from api.models import RuleConfigRow as RCR
    # Lazy import to avoid a circular import at module load time
    if existing:
        db.execute(
            "INSERT INTO rule_config_history (audit_session_id, changed_by, previous_json, new_json) "
            "VALUES (:sid, :uid, :prev, :new)",
            {"sid": session_id, "uid": str(user.id), "prev": existing.config_json, "new": body.config},
        )
        existing.config_json = body.config
        existing.updated_by = user.id
    else:
        db.add(RCR(audit_session_id=session_id, config_json=body.config, updated_by=user.id))
    db.commit()
    return {"status": "updated"}
