"""
§5.1 Duplicates — ported exactly from the prototype, thresholds now config-driven.

Item-level rule (primary):
  Flag duplicates where INSURANCE_MEMBER_ID appears more than once AND
  MEDICAL_PRODUCT_NAME is similar, within a `duplicate_day_window`-day window
  of the FIRST DATE_VISIT_STARTED in that group. Different product for the
  same member is NOT a duplicate. Only rows with ITEM_STATUS in
  `duplicate_eligible_item_statuses` are eligible.

Algorithm:
  1. Filter to eligible rows (status check).
  2. Group by member ID.
  3. Within each member's rows, sort by visit date ascending.
  4. Cluster forward: for each row not yet in a cluster, open a new cluster
     anchored on it, then pull in any later row within the day-window of the
     ANCHOR's date whose product-name similarity to the anchor is >= the
     threshold. (Matches prototype behavior: window is measured from the
     first/earliest item in the group, not chained from the previous item.)
  5. Any cluster with >1 member is a duplicate group.

Claim-level fallback (for extracts without item-level fields):
  Flag repeated invoice number, or repeated member + diagnosis + date.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .config import RuleConfig, DEFAULT_CONFIG
from .similarity import hybrid_similarity


@dataclass
class DuplicateFlag:
    row_indices: List[int]
    group_id: str
    member_id: str
    anchor_date: Any
    days_from_first_visit: List[int]
    similarity_scores: List[float]  # similarity of each member to the anchor
    products: List[str]


def detect_item_level_duplicates(
    rows: List[Dict[str, Any]],
    config: RuleConfig = DEFAULT_CONFIG,
) -> List[DuplicateFlag]:
    """
    rows: list of dicts, each expected to have (after column mapping):
      'row_index', 'member_id', 'product_name', 'visit_date' (date obj), 'item_status'
    """
    eligible_statuses = {s.lower() for s in config.duplicate_eligible_item_statuses}
    eligible = [
        r for r in rows
        if str(r.get("item_status", "")).strip().lower() in eligible_statuses
    ]

    by_member: Dict[str, List[Dict[str, Any]]] = {}
    for r in eligible:
        by_member.setdefault(r["member_id"], []).append(r)

    flags: List[DuplicateFlag] = []
    group_counter = 0

    for member_id, member_rows in by_member.items():
        if len(member_rows) < 2:
            continue

        member_rows = sorted(member_rows, key=lambda r: r["visit_date"])
        used = [False] * len(member_rows)

        for i in range(len(member_rows)):
            if used[i]:
                continue
            anchor = member_rows[i]
            anchor_date = anchor["visit_date"]
            cluster = [i]
            used[i] = True

            for j in range(i + 1, len(member_rows)):
                if used[j]:
                    continue
                candidate = member_rows[j]
                delta_days = (candidate["visit_date"] - anchor_date).days
                if delta_days > config.duplicate_day_window:
                    # rows are sorted ascending, so once we're past the
                    # window we can stop scanning forward for this anchor
                    break
                score = hybrid_similarity(
                    anchor["product_name"], candidate["product_name"]
                )
                if score >= config.duplicate_similarity_threshold:
                    cluster.append(j)
                    used[j] = True

            if len(cluster) > 1:
                group_counter += 1
                flags.append(
                    DuplicateFlag(
                        row_indices=[member_rows[k]["row_index"] for k in cluster],
                        group_id=f"DUP-{group_counter:06d}",
                        member_id=member_id,
                        anchor_date=anchor_date,
                        days_from_first_visit=[
                            (member_rows[k]["visit_date"] - anchor_date).days
                            for k in cluster
                        ],
                        similarity_scores=[
                            hybrid_similarity(
                                anchor["product_name"],
                                member_rows[k]["product_name"],
                            )
                            for k in cluster
                        ],
                        products=[member_rows[k]["product_name"] for k in cluster],
                    )
                )

    return flags


@dataclass
class ClaimDuplicateFlag:
    row_indices: List[int]
    group_id: str
    reason: str  # "repeated_invoice" or "repeated_member_diagnosis_date"


def detect_claim_level_duplicates(
    rows: List[Dict[str, Any]],
) -> List[ClaimDuplicateFlag]:
    """
    Fallback for claim-level extracts lacking item-level fields.
    rows expected to have: 'row_index', 'member_id', optionally
    'invoice_number', 'diagnosis_name', 'claim_date'.
    """
    flags: List[ClaimDuplicateFlag] = []
    group_counter = 0

    # Repeated invoice number
    by_invoice: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        inv = r.get("invoice_number")
        if inv:
            by_invoice.setdefault(inv, []).append(r)
    for inv, group in by_invoice.items():
        if len(group) > 1:
            group_counter += 1
            flags.append(ClaimDuplicateFlag(
                row_indices=[r["row_index"] for r in group],
                group_id=f"CDUP-{group_counter:06d}",
                reason="repeated_invoice",
            ))

    # Repeated member + diagnosis + date
    by_mdd: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r.get("member_id"), r.get("diagnosis_name"), r.get("claim_date"))
        if all(key):
            by_mdd.setdefault(key, []).append(r)
    for key, group in by_mdd.items():
        if len(group) > 1:
            group_counter += 1
            flags.append(ClaimDuplicateFlag(
                row_indices=[r["row_index"] for r in group],
                group_id=f"CDUP-{group_counter:06d}",
                reason="repeated_member_diagnosis_date",
            ))

    return flags
