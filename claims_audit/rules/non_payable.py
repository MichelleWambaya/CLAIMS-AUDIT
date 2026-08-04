"""
§5.2 Non-payable categories.

Match against BOTH MEDICAL_PRODUCT_NAME and DIAGNOSIS_NAME (case-insensitive
substring match) — item-level extracts carry the relevant text in the
product field, claim-level extracts carry it in the diagnosis field.

Only rows with ITEM_STATUS = Approved are eligible WHEN that column exists
in the file; extracts without an ITEM_STATUS column are not gated (i.e. if
the file has no item_status field at all, every row is eligible).

Known limitation (surface in UI): keyword matching, not clinical coding.
Cannot distinguish wellness-use supplements from a prescribed deficiency
treatment, or menopause HRT from post-surgical HRT with a genuine medical
indication. Provide the override/exception path in the review UI (tracked
separately in the DB, see db/schema.sql `flag_overrides`) rather than by
editing the keyword library.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import RuleConfig, DEFAULT_CONFIG


@dataclass
class NonPayableFlag:
    row_index: int
    category: str
    matched_keyword: str
    matched_field: str  # "product_name" or "diagnosis_name"


def detect_non_payable(
    rows: List[Dict[str, Any]],
    config: RuleConfig = DEFAULT_CONFIG,
) -> List[NonPayableFlag]:
    """
    rows: list of dicts with 'row_index', optional 'product_name',
    optional 'diagnosis_name', optional 'item_status'.
    `has_item_status_column` should be True if the source file had that
    column at all (distinct from the value being blank on a given row).
    """
    eligible_statuses = {s.lower() for s in config.non_payable_eligible_item_statuses}

    # Pre-lowercase keyword lists once.
    keyword_lookup = {
        category: [kw.lower() for kw in keywords]
        for category, keywords in config.non_payable_keywords.items()
    }

    flags: List[NonPayableFlag] = []

    for r in rows:
        has_status_col = r.get("_has_item_status_column", True)
        if has_status_col:
            status = str(r.get("item_status", "")).strip().lower()
            if status not in eligible_statuses:
                continue

        for field_name in ("product_name", "diagnosis_name"):
            value = r.get(field_name)
            if not value:
                continue
            value_lower = str(value).lower()
            for category, keywords in keyword_lookup.items():
                for kw in keywords:
                    if kw in value_lower:
                        flags.append(NonPayableFlag(
                            row_index=r["row_index"],
                            category=category,
                            matched_keyword=kw,
                            matched_field=field_name,
                        ))
                        # one match per category per field is enough; move
                        # on to the next category (row can hit >1 category,
                        # and can match independently in both fields)
                        break

    return flags
