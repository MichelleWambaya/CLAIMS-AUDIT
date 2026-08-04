"""
§5.4 Invalid member/policy, and §5.5 Diagnosis/coding gaps.

Policy number expected shape (default): PREFIX/YY/CODE/000000/00
  - alpha prefix
  - 2-digit year
  - alphanumeric code
  - 6-digit numeric sequence
  - 2-digit numeric sub-sequence

Format is regex-driven and configurable per payer, since different schemes
(different insurers, or AAR's own historical formats) may use different
conventions. See RuleConfig.policy_regex_by_payer.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import RuleConfig, DEFAULT_CONFIG


@dataclass
class MemberPolicyFlag:
    row_index: int
    reason: str  # "missing_membership_number" | "missing_policy_number" | "invalid_policy_format"
    policy_number: Optional[str]


def _regex_for_payer(payer: Optional[str], config: RuleConfig) -> str:
    if payer and payer in config.policy_regex_by_payer:
        return config.policy_regex_by_payer[payer]
    return config.policy_regex_by_payer.get(
        "default", r"^[A-Za-z]+/\d{2}/[A-Za-z0-9]+/\d{6}/\d{2}$"
    )


def detect_invalid_member_policy(
    rows: List[Dict[str, Any]],
    config: RuleConfig = DEFAULT_CONFIG,
) -> List[MemberPolicyFlag]:
    """
    rows: list of dicts with 'row_index', optional 'membership_number',
    optional 'policy_number', optional 'payer'.
    """
    flags: List[MemberPolicyFlag] = []

    for r in rows:
        membership = r.get("membership_number")
        policy = r.get("policy_number")
        payer = r.get("payer")

        if not membership or not str(membership).strip():
            flags.append(MemberPolicyFlag(
                row_index=r["row_index"],
                reason="missing_membership_number",
                policy_number=policy,
            ))

        if not policy or not str(policy).strip():
            flags.append(MemberPolicyFlag(
                row_index=r["row_index"],
                reason="missing_policy_number",
                policy_number=policy,
            ))
            continue  # can't format-check an empty value

        pattern = _regex_for_payer(payer, config)
        if not re.match(pattern, str(policy).strip()):
            flags.append(MemberPolicyFlag(
                row_index=r["row_index"],
                reason="invalid_policy_format",
                policy_number=policy,
            ))

    return flags


@dataclass
class DiagnosisGapFlag:
    row_index: int
    reason: str  # "missing_diagnosis_name" | "missing_diagnosis_type"


def detect_diagnosis_gaps(rows: List[Dict[str, Any]]) -> List[DiagnosisGapFlag]:
    """
    rows: list of dicts with 'row_index', optional 'diagnosis_name',
    optional 'diagnosis_type'.
    """
    flags: List[DiagnosisGapFlag] = []
    for r in rows:
        if not r.get("diagnosis_name") or not str(r["diagnosis_name"]).strip():
            flags.append(DiagnosisGapFlag(
                row_index=r["row_index"], reason="missing_diagnosis_name"
            ))
        if not r.get("diagnosis_type") or not str(r["diagnosis_type"]).strip():
            flags.append(DiagnosisGapFlag(
                row_index=r["row_index"], reason="missing_diagnosis_type"
            ))
    return flags
