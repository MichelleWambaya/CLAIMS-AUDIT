"""
Overpaid claims — rate-card lookup against the "agreed price lists"
workbook. This is a DIFFERENT rule from pricing.py's IQR statistical
outlier check: this compares each claim's billed unit price directly
against a contracted rate, not against the distribution of prices in its
own category.

Matching logic (exact/substring, per your confirmation — no fuzzy
similarity here, unlike the duplicate-detection rule):
  1. PROVIDER_AFFILIATION on the claim selects which worksheet in the
     agreed-price workbook to check against (worksheet name comparable to
     PROVIDER_AFFILIATION — case-insensitive, whitespace-normalized match,
     since sheet names rarely match a provider string byte-for-byte).
  2. Within that worksheet, MEDICAL_PRODUCT_NAME is matched against the
     "Service Description" column — exact match first; if none, a
     case-insensitive substring match in either direction (claim product
     name contains the service description, or vice versa) so minor
     wording differences ("Consultation - General" vs "General
     Consultation") don't silently fail to match.
  3. If a matching row is found, ITEM_UNIT_PRICE on the claim is compared
     to that row's "Agreed Rate". Any amount strictly above the agreed
     rate is flagged as overpaid, with the delta reported.
  4. Claims whose PROVIDER_AFFILIATION has no matching worksheet, or whose
     product has no matching service description within that worksheet,
     are NOT flagged — there's no agreed rate to compare against, so
     silence here means "no rate on file," not "compliant." Both cases
     are reported separately (see `unmatched_provider` / `unmatched_service`
     in the returned summary) so the gap itself is visible to an analyst,
     rather than disappearing into a false "no overpayment found."

Known limitation (substring ≠ fuzzy): word ORDER matters. "General
Consultation" only matches product names that contain that exact phrase
as a run of characters — "Consultation, General" or "Consultation for
General Checkup" will NOT match despite meaning the same thing, since
that would require token-level comparison (the similarity.py approach
used for duplicates), which you asked to exclude here. If real data turns
out to have a lot of reordered/abbreviated service names, that's exactly
where it will show up in `unmatched_service_rows` — worth checking that
list, not just the flagged overpayments, once real files are loaded.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _normalize_provider_name(name: str) -> str:
    return re.sub(r"[\s_\-]+", " ", str(name).strip().lower())


def _normalize_service_text(name: str) -> str:
    text = str(name).strip().lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@dataclass
class AgreedRateEntry:
    service_description: str
    agreed_rate: float


@dataclass
class AgreedRateBook:
    """In-memory representation of the 'agreed price lists' workbook:
    one list of (service_description, agreed_rate) pairs per worksheet,
    keyed by normalized worksheet/provider name."""
    sheets: Dict[str, List[AgreedRateEntry]] = field(default_factory=dict)

    @classmethod
    def from_worksheets(cls, worksheets: Dict[str, List[Dict[str, Any]]]) -> "AgreedRateBook":
        """
        worksheets: {sheet_name: [ {"service_description": ..., "agreed_rate": ...}, ... ]}
        i.e. the already-parsed contents of each sheet in the agreed
        price list workbook, one entry per row.
        """
        book = cls()
        for sheet_name, rows in worksheets.items():
            key = _normalize_provider_name(sheet_name)
            book.sheets[key] = [
                AgreedRateEntry(
                    service_description=str(r.get("service_description", "")),
                    agreed_rate=float(r["agreed_rate"]),
                )
                for r in rows
                if r.get("service_description") and r.get("agreed_rate") is not None
            ]
        return book

    def find_sheet(self, provider_affiliation: str) -> Optional[List[AgreedRateEntry]]:
        key = _normalize_provider_name(provider_affiliation)
        if key in self.sheets:
            return self.sheets[key]
        # fall back to substring match in case the sheet name is a
        # shortened/expanded version of the provider string
        for sheet_key, entries in self.sheets.items():
            if sheet_key in key or key in sheet_key:
                return entries
        return None

    def find_rate(self, entries: List[AgreedRateEntry], product_name: str) -> Optional[AgreedRateEntry]:
        norm_product = _normalize_service_text(product_name)
        # exact match first
        for entry in entries:
            if _normalize_service_text(entry.service_description) == norm_product:
                return entry
        # substring match, either direction
        for entry in entries:
            norm_service = _normalize_service_text(entry.service_description)
            if norm_service and (norm_service in norm_product or norm_product in norm_service):
                return entry
        return None


@dataclass
class OverpaidClaimFlag:
    row_index: int
    provider_affiliation: str
    product_name: str
    billed_unit_price: float
    agreed_rate: float
    overpaid_amount: float
    matched_service_description: str


@dataclass
class RateMatchSummary:
    overpaid: List[OverpaidClaimFlag]
    unmatched_provider_rows: List[int]   # no worksheet found for this provider
    unmatched_service_rows: List[int]    # worksheet found, but no service description matched


def detect_overpaid_claims(
    rows: List[Dict[str, Any]],
    rate_book: AgreedRateBook,
) -> RateMatchSummary:
    """
    rows: list of dicts with 'row_index', 'provider_affiliation',
    'product_name', 'unit_price'.
    """
    overpaid: List[OverpaidClaimFlag] = []
    unmatched_provider_rows: List[int] = []
    unmatched_service_rows: List[int] = []

    for r in rows:
        provider = r.get("provider_affiliation")
        product = r.get("product_name")
        unit_price = r.get("unit_price")
        if not provider or not product or unit_price is None:
            continue

        entries = rate_book.find_sheet(provider)
        if entries is None:
            unmatched_provider_rows.append(r["row_index"])
            continue

        match = rate_book.find_rate(entries, product)
        if match is None:
            unmatched_service_rows.append(r["row_index"])
            continue

        unit_price = float(unit_price)
        if unit_price > match.agreed_rate:
            overpaid.append(OverpaidClaimFlag(
                row_index=r["row_index"],
                provider_affiliation=provider,
                product_name=product,
                billed_unit_price=unit_price,
                agreed_rate=match.agreed_rate,
                overpaid_amount=round(unit_price - match.agreed_rate, 2),
                matched_service_description=match.service_description,
            ))

    return RateMatchSummary(
        overpaid=overpaid,
        unmatched_provider_rows=unmatched_provider_rows,
        unmatched_service_rows=unmatched_service_rows,
    )
