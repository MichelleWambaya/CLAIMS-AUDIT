from .config import RuleConfig, DEFAULT_CONFIG, DEFAULT_NON_PAYABLE_KEYWORDS
from .similarity import hybrid_similarity, levenshtein_ratio, jaccard_token_similarity
from .duplicates import (
    detect_item_level_duplicates,
    detect_claim_level_duplicates,
    DuplicateFlag,
    ClaimDuplicateFlag,
)
from .non_payable import detect_non_payable, NonPayableFlag
from .pricing import detect_pricing_anomalies, PricingAnomalyFlag
from .member_policy import (
    detect_invalid_member_policy,
    detect_diagnosis_gaps,
    MemberPolicyFlag,
    DiagnosisGapFlag,
)
from .column_mapping import map_headers, detect_missing_expected_columns, DEFAULT_ALIASES
from .overpaid_claims import (
    AgreedRateBook, AgreedRateEntry, detect_overpaid_claims,
    OverpaidClaimFlag, RateMatchSummary,
)

__all__ = [
    "RuleConfig", "DEFAULT_CONFIG", "DEFAULT_NON_PAYABLE_KEYWORDS",
    "hybrid_similarity", "levenshtein_ratio", "jaccard_token_similarity",
    "detect_item_level_duplicates", "detect_claim_level_duplicates",
    "DuplicateFlag", "ClaimDuplicateFlag",
    "detect_non_payable", "NonPayableFlag",
    "detect_pricing_anomalies", "PricingAnomalyFlag",
    "detect_invalid_member_policy", "detect_diagnosis_gaps",
    "MemberPolicyFlag", "DiagnosisGapFlag",
    "map_headers", "detect_missing_expected_columns", "DEFAULT_ALIASES",
    "AgreedRateBook", "AgreedRateEntry", "detect_overpaid_claims",
    "OverpaidClaimFlag", "RateMatchSummary",
]


def run_all_rules(item_rows, claim_rows, config: RuleConfig = DEFAULT_CONFIG) -> dict:
    """
    Convenience entrypoint a background worker would call after merging a
    batch into the audit session's dataset. Pass whichever of item_rows /
    claim_rows are present for this extract type (either can be []).
    """
    results = {
        "item_level_duplicates": [],
        "claim_level_duplicates": [],
        "non_payable": [],
        "pricing_anomalies": [],
        "invalid_member_policy": [],
        "diagnosis_gaps": [],
    }

    if item_rows:
        results["item_level_duplicates"] = detect_item_level_duplicates(item_rows, config)
        results["non_payable"] = detect_non_payable(item_rows, config)

    if claim_rows:
        results["claim_level_duplicates"] = detect_claim_level_duplicates(claim_rows)
        results["non_payable"].extend(detect_non_payable(claim_rows, config))
        results["pricing_anomalies"] = detect_pricing_anomalies(claim_rows, config)
        results["invalid_member_policy"] = detect_invalid_member_policy(claim_rows, config)
        results["diagnosis_gaps"] = detect_diagnosis_gaps(claim_rows)

    return results
