"""
§5.6 Column mapping.

Map incoming raw headers to canonical field names by alias list,
case-insensitive, punctuation/whitespace-insensitive. Admins extend the
alias lists (stored in a `column_aliases` table in production, see
db/schema.sql) to onboard a new payer/extract format without a code change.
"""
import re
from typing import Dict, List, Optional

# canonical_field -> known raw header aliases (seed data)
DEFAULT_ALIASES: Dict[str, List[str]] = {
    "member_id": [
        "insurance_member_id", "membership_number", "member_id", "member_no",
        "insurance member id",
    ],
    "policy_number": ["policy_number", "policy_no", "policy #"],
    "claim_code": ["claim_code", "claim_no", "claim_number"],
    "payer": ["payer_name", "payer", "insurer"],
    "category": ["category", "benefit_category"],
    "plan": ["plan", "plan_name", "product_plan"],
    "claim_date": ["date_claim_created", "claim_date", "date_created"],
    "diagnosis_type": ["diagnosis_type", "dx_type"],
    "diagnosis_name": ["diagnosis_name", "diagnosis", "dx_name", "dx"],
    "invoice_number": ["invoice_number", "invoice_no", "invoice #"],
    "amount": ["amount", "claim_amount", "billed_amount", "total_amount"],
    "provider": ["provider", "provider_name", "facility", "facility_name"],
    "product_name": [
        "medical_product_name", "product_name", "item_name", "service_name",
    ],
    "visit_date": ["date_visit_started", "visit_date", "date_of_visit"],
    "item_status": ["item_status", "status", "claim_item_status"],
}


def _normalize_header(h: str) -> str:
    h = h.strip().lower()
    h = re.sub(r"[\s_\-]+", "_", h)
    h = re.sub(r"[^a-z0-9_#]", "", h)
    return h


def build_alias_lookup(
    aliases: Dict[str, List[str]] = DEFAULT_ALIASES
) -> Dict[str, str]:
    """Flatten canonical->aliases into normalized_alias -> canonical."""
    lookup: Dict[str, str] = {}
    for canonical, alias_list in aliases.items():
        for alias in alias_list + [canonical]:
            lookup[_normalize_header(alias)] = canonical
    return lookup


def map_headers(
    raw_headers: List[str],
    aliases: Dict[str, List[str]] = DEFAULT_ALIASES,
) -> Dict[str, Optional[str]]:
    """
    Returns raw_header -> canonical_field (or None if unmapped).
    Unmapped columns are preserved as-is in the merged dataset (not
    dropped) so nothing is silently lost, they just don't participate
    in the flag rules.
    """
    lookup = build_alias_lookup(aliases)
    result: Dict[str, Optional[str]] = {}
    for raw in raw_headers:
        result[raw] = lookup.get(_normalize_header(raw))
    return result


def detect_missing_expected_columns(
    mapped: Dict[str, Optional[str]],
    required_canonical_fields: List[str],
) -> List[str]:
    """Given a header mapping, return which required canonical fields were
    not found in this file at all — used for the per-file schema validation
    in §4 ("missing expected columns ... per file before merging")."""
    present = set(v for v in mapped.values() if v is not None)
    return [f for f in required_canonical_fields if f not in present]
