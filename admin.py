"""
Admin-only configuration endpoints (build prompt: "Every threshold above
must be admin-editable without a redeploy, with a change history").

Deliberately contains NO schema-bootstrap or user-bootstrap endpoints —
schema is applied automatically at process startup (api/db.py:apply_schema,
called from api/main.py), and accounts are created through the real
signup flow in api/routers/auth.py. See DEPLOYMENT.md / README.md for why
the previous version's browser-address-bar bootstrap endpoints were
removed.
"""
import dataclasses
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import RuleConfigRow, User
from auth.security import require_admin, get_current_user
from rules.config import RuleConfig, DEFAULT_CONFIG

router = APIRouter(prefix="/admin", tags=["admin"])


def _load_config(db: Session, session_id: str) -> dict:
    row = db.query(RuleConfigRow).filter(RuleConfigRow.audit_session_id == session_id).first()
    if row:
        return row.config_json
    return dataclasses.asdict(DEFAULT_CONFIG)


@router.get("/sessions/{session_id}/rule-config")
def get_rule_config(session_id: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Any authenticated user (analyst or admin) can view current thresholds."""
    return _load_config(db, session_id)


class RuleConfigUpdate(BaseModel):
    config: Dict[str, Any]


@router.put("/sessions/{session_id}/rule-config")
def update_rule_config(session_id: str, body: RuleConfigUpdate, db: Session = Depends(get_db),
                        admin: User = Depends(require_admin)):
    """Admin-only. Validates the new config against the RuleConfig
    dataclass shape (so a typo can't silently produce a dead threshold),
    persists it, and records who changed what and when."""
    try:
        RuleConfig(**body.config)  # shape/type validation
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid rule config: {e}")

    from api.models import AuditSession
    if not db.query(AuditSession).filter(AuditSession.id == session_id).first():
        raise HTTPException(status_code=404, detail="Audit session not found")

    previous = _load_config(db, session_id)
    row = db.query(RuleConfigRow).filter(RuleConfigRow.audit_session_id == session_id).first()
    if row:
        row.config_json = body.config
        row.updated_by = admin.id
    else:
        row = RuleConfigRow(audit_session_id=session_id, config_json=body.config, updated_by=admin.id)
        db.add(row)

    from api.models import RuleConfigHistory
    db.add(RuleConfigHistory(
        audit_session_id=session_id,
        changed_by=admin.id,
        previous_json=previous,
        new_json=body.config,
    ))
    db.commit()
    return {"updated": True, "config": body.config}


@router.get("/sessions/{session_id}/rule-config/history")
def get_rule_config_history(session_id: str, db: Session = Depends(get_db),
                             user: User = Depends(get_current_user)):
    from api.models import RuleConfigHistory
    rows = (
        db.query(RuleConfigHistory)
        .filter(RuleConfigHistory.audit_session_id == session_id)
        .order_by(RuleConfigHistory.changed_at.desc())
        .all()
    )
    return [
        {
            "id": r.id, "changed_by": str(r.changed_by), "changed_at": r.changed_at.isoformat(),
            "previous_json": r.previous_json, "new_json": r.new_json,
        }
        for r in rows
    ]


# --- Non-payable keyword library (admin-editable per build prompt §5.2) ---

class KeywordCreate(BaseModel):
    category: str
    keyword: str


@router.get("/non-payable-keywords")
def list_keywords(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from api.models import NonPayableKeyword
    rows = db.query(NonPayableKeyword).order_by(NonPayableKeyword.category, NonPayableKeyword.keyword).all()
    out: Dict[str, list] = {}
    for r in rows:
        out.setdefault(r.category, []).append({"id": r.id, "keyword": r.keyword})
    return out


@router.post("/non-payable-keywords")
def add_keyword(body: KeywordCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from api.models import NonPayableKeyword
    existing = (
        db.query(NonPayableKeyword)
        .filter(NonPayableKeyword.category == body.category, NonPayableKeyword.keyword == body.keyword)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Keyword already exists in this category")
    row = NonPayableKeyword(category=body.category, keyword=body.keyword, added_by=admin.id)
    db.add(row)
    db.commit()
    return {"id": row.id, "category": row.category, "keyword": row.keyword}


@router.delete("/non-payable-keywords/{keyword_id}")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from api.models import NonPayableKeyword
    row = db.query(NonPayableKeyword).filter(NonPayableKeyword.id == keyword_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Keyword not found")
    db.delete(row)
    db.commit()
    return {"deleted": True}
