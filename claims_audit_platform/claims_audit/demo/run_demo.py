"""
Sanity-check demo for the rule engine — run with:
    python3 demo/run_demo.py
from the claims_audit/ directory.

Covers each rule with at least one row that SHOULD flag and one that
SHOULD NOT, so regressions are obvious.
"""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules import (
    detect_item_level_duplicates,
    detect_claim_level_duplicates,
    detect_non_payable,
    detect_pricing_anomalies,
    detect_invalid_member_policy,
    detect_diagnosis_gaps,
    map_headers,
    DEFAULT_CONFIG,
)


def section(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------
section("5.1 Item-level duplicates")
# ---------------------------------------------------------------------
item_rows = [
    # Real duplicate: same member, same drug (reordered wording), 2 days apart
    {"row_index": 1, "member_id": "M001", "product_name": "Panadol Extra 500mg Tablets",
     "visit_date": date(2026, 1, 1), "item_status": "Approved"},
    {"row_index": 2, "member_id": "M001", "product_name": "Panadol Extra Tablets 500mg",
     "visit_date": date(2026, 1, 3), "item_status": "Approved"},

    # Same member, different product entirely -> NOT a duplicate
    {"row_index": 3, "member_id": "M001", "product_name": "Amoxicillin 250mg",
     "visit_date": date(2026, 1, 4), "item_status": "Approved"},

    # Same member/product but 10 days later, outside the 5-day window -> NOT flagged
    {"row_index": 4, "member_id": "M001", "product_name": "Panadol Extra 500mg Tablets",
     "visit_date": date(2026, 1, 14), "item_status": "Approved"},

    # Not eligible: status isn't Approved
    {"row_index": 5, "member_id": "M002", "product_name": "Ibuprofen 400mg",
     "visit_date": date(2026, 1, 1), "item_status": "Pending"},
    {"row_index": 6, "member_id": "M002", "product_name": "Ibuprofen 400mg",
     "visit_date": date(2026, 1, 2), "item_status": "Pending"},
]
dup_flags = detect_item_level_duplicates(item_rows, DEFAULT_CONFIG)
for f in dup_flags:
    print(f"  {f.group_id}: member={f.member_id} rows={f.row_indices} "
          f"products={f.products} similarity={[round(s,2) for s in f.similarity_scores]}")
assert len(dup_flags) == 1, f"expected 1 duplicate cluster, got {len(dup_flags)}"
assert dup_flags[0].row_indices == [1, 2]
print("  PASS")


# ---------------------------------------------------------------------
section("5.1 Claim-level fallback duplicates")
# ---------------------------------------------------------------------
claim_rows_for_dup = [
    {"row_index": 10, "member_id": "M010", "invoice_number": "INV-100",
     "diagnosis_name": "Malaria", "claim_date": date(2026, 2, 1)},
    {"row_index": 11, "member_id": "M010", "invoice_number": "INV-100",
     "diagnosis_name": "Malaria", "claim_date": date(2026, 2, 1)},
    {"row_index": 12, "member_id": "M011", "invoice_number": "INV-200",
     "diagnosis_name": "Flu", "claim_date": date(2026, 2, 2)},
]
claim_dup_flags = detect_claim_level_duplicates(claim_rows_for_dup)
for f in claim_dup_flags:
    print(f"  {f.group_id}: reason={f.reason} rows={f.row_indices}")
# Rows 10/11 share both invoice AND member+diagnosis+date, so they
# legitimately trip both fallback checks -> 2 flags, same underlying pair.
assert len(claim_dup_flags) == 2
assert all(f.row_indices == [10, 11] for f in claim_dup_flags)
print("  PASS")


# ---------------------------------------------------------------------
section("5.2 Non-payable categories")
# ---------------------------------------------------------------------
np_rows = [
    {"row_index": 20, "product_name": "CeraVe Moisturizing Cream", "diagnosis_name": None,
     "item_status": "Approved"},
    {"row_index": 21, "product_name": "Amoxicillin 250mg", "diagnosis_name": "Bacterial infection",
     "item_status": "Approved"},
    {"row_index": 22, "product_name": None, "diagnosis_name": "COVID-19 pandemic related illness",
     "item_status": "Approved"},
    # Not eligible: status not Approved
    {"row_index": 23, "product_name": "Invisalign clear aligner", "diagnosis_name": None,
     "item_status": "Rejected"},
    # No item_status column at all -> not gated, should still flag
    {"row_index": 24, "product_name": "Multivitamin tablets", "diagnosis_name": None,
     "_has_item_status_column": False},
]
np_flags = detect_non_payable(np_rows, DEFAULT_CONFIG)
for f in np_flags:
    print(f"  row={f.row_index} category={f.category} field={f.matched_field} kw='{f.matched_keyword}'")
flagged_rows = {f.row_index for f in np_flags}
assert flagged_rows == {20, 22, 24}, flagged_rows
print("  PASS")


# ---------------------------------------------------------------------
section("5.3 Pricing anomalies (IQR)")
# ---------------------------------------------------------------------
pricing_rows = [
    {"row_index": i, "category": "Outpatient", "amount": amt}
    for i, amt in enumerate([1000, 1100, 1050, 1200, 1150, 1080, 25000], start=30)
]
price_flags = detect_pricing_anomalies(pricing_rows, DEFAULT_CONFIG)
for f in price_flags:
    print(f"  row={f.row_index} amount={f.amount} threshold={round(f.threshold,2)}")
assert len(price_flags) == 1 and price_flags[0].row_index == 36
print("  PASS")


# ---------------------------------------------------------------------
section("5.4 Invalid member/policy")
# ---------------------------------------------------------------------
policy_rows = [
    {"row_index": 40, "membership_number": "MB123", "policy_number": "AAR/26/GRP/000123/01"},
    {"row_index": 41, "membership_number": "MB124", "policy_number": "BADFORMAT"},
    {"row_index": 42, "membership_number": "", "policy_number": "AAR/26/GRP/000123/01"},
    {"row_index": 43, "membership_number": "MB125", "policy_number": ""},
]
policy_flags = detect_invalid_member_policy(policy_rows, DEFAULT_CONFIG)
for f in policy_flags:
    print(f"  row={f.row_index} reason={f.reason}")
reasons_by_row = {}
for f in policy_flags:
    reasons_by_row.setdefault(f.row_index, []).append(f.reason)
assert 40 not in reasons_by_row
assert reasons_by_row[41] == ["invalid_policy_format"]
assert reasons_by_row[42] == ["missing_membership_number"]
assert reasons_by_row[43] == ["missing_policy_number"]
print("  PASS")


# ---------------------------------------------------------------------
section("5.5 Diagnosis gaps")
# ---------------------------------------------------------------------
dx_rows = [
    {"row_index": 50, "diagnosis_name": "Malaria", "diagnosis_type": "Primary"},
    {"row_index": 51, "diagnosis_name": "", "diagnosis_type": "Primary"},
    {"row_index": 52, "diagnosis_name": "Flu", "diagnosis_type": ""},
]
dx_flags = detect_diagnosis_gaps(dx_rows)
for f in dx_flags:
    print(f"  row={f.row_index} reason={f.reason}")
assert len(dx_flags) == 2
print("  PASS")


# ---------------------------------------------------------------------
section("5.6 Column mapping (alias-based, header-name agnostic)")
# ---------------------------------------------------------------------
raw_headers = [
    "INSURANCE_MEMBER_ID", "Medical Product Name", "date_visit_started",
    "Some Unrelated Custom Column",
]
mapped = map_headers(raw_headers)
for raw, canon in mapped.items():
    print(f"  '{raw}' -> {canon}")
assert mapped["INSURANCE_MEMBER_ID"] == "member_id"
assert mapped["Medical Product Name"] == "product_name"
assert mapped["date_visit_started"] == "visit_date"
assert mapped["Some Unrelated Custom Column"] is None
print("  PASS")

print("\nAll rule-engine checks passed.\n")


# ---------------------------------------------------------------------
section("Overpaid claims — agreed price list lookup (exact/substring match)")
# ---------------------------------------------------------------------
from rules.overpaid_claims import AgreedRateBook, detect_overpaid_claims

# Mimics the "agreed price lists" workbook: one worksheet per provider.
agreed_price_worksheets = {
    "Nairobi Hospital": [
        {"service_description": "General Consultation", "agreed_rate": 1500},
        {"service_description": "Full Blood Count", "agreed_rate": 800},
    ],
    "Aga Khan University Hospital": [
        {"service_description": "General Consultation", "agreed_rate": 2000},
        {"service_description": "Malaria Test (RDT)", "agreed_rate": 500},
    ],
}
rate_book = AgreedRateBook.from_worksheets(agreed_price_worksheets)

# Mimics rows from "2025 claims processed in Jun 2026".
claim_rows_for_rates = [
    # Exact match, billed above agreed rate -> overpaid
    {"row_index": 60, "provider_affiliation": "Nairobi Hospital",
     "product_name": "General Consultation", "unit_price": 2500},
    # Substring match ("General Consultation - Follow Up" contains the
    # agreed service description as a literal substring), within rate -> not flagged
    {"row_index": 61, "provider_affiliation": "Aga Khan University Hospital",
     "product_name": "General Consultation - Follow Up", "unit_price": 1800},
    # Exact match, billed within/at agreed rate -> not flagged
    {"row_index": 62, "provider_affiliation": "Nairobi Hospital",
     "product_name": "Full Blood Count", "unit_price": 800},
    # No worksheet for this provider -> unmatched_provider, not flagged either way
    {"row_index": 63, "provider_affiliation": "Unknown Clinic Ltd",
     "product_name": "General Consultation", "unit_price": 5000},
    # Worksheet found, but no service description matches -> unmatched_service
    {"row_index": 64, "provider_affiliation": "Nairobi Hospital",
     "product_name": "Advanced MRI Scan", "unit_price": 12000},
]

summary = detect_overpaid_claims(claim_rows_for_rates, rate_book)
for f in summary.overpaid:
    print(f"  OVERPAID row={f.row_index} provider={f.provider_affiliation} "
          f"billed={f.billed_unit_price} agreed={f.agreed_rate} over_by={f.overpaid_amount}")
print(f"  unmatched_provider_rows={summary.unmatched_provider_rows}")
print(f"  unmatched_service_rows={summary.unmatched_service_rows}")

assert [f.row_index for f in summary.overpaid] == [60]
assert summary.overpaid[0].overpaid_amount == 1000.0
assert summary.unmatched_provider_rows == [63]
assert summary.unmatched_service_rows == [64]
print("  PASS")

print("\nAll checks (including overpaid-claims rate lookup) passed.\n")
