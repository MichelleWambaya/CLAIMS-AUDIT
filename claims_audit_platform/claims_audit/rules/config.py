"""
Central, admin-editable configuration for every threshold referenced in
Build Prompt §5. In production this should be loaded from the `rule_config`
table (see db/schema.sql) so admins can change values with no deploy,
with every change recorded in `rule_config_history`.

Nothing in rules/*.py should hardcode a number or keyword — it should
receive a RuleConfig instance.
"""
from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# §5.2 Non-payable keyword library (seed data — lives in an editable table
# in production, this is just the default seed).
# ---------------------------------------------------------------------------
DEFAULT_NON_PAYABLE_KEYWORDS: Dict[str, List[str]] = {
    "Cosmetics": [
        "cosmetic", "la roche", "la roche-posay", "laroche", "vichy", "avene",
        "eucerin", "cetaphil", "nivea", "l'oreal", "loreal", "olay",
        "neutrogena", "clinique", "estee lauder", "lancome", "bioderma",
        "cerave", "garnier", "clarins", "elizabeth arden", "skinceuticals",
        "ponds", "the ordinary", "whitening cream", "anti-aging cream",
        "anti ageing cream", "anti wrinkle cream", "skin lightening",
        "beauty cream",
    ],
    "Plastic Surgery": [
        "liposuction", "rhinoplasty", "face lift", "facelift", "tummy tuck",
        "abdominoplasty", "breast augmentation", "breast implant",
        "blepharoplasty", "otoplasty", "mommy makeover", "cosmetic surgery",
        "plastic surgery", "dermal filler", "lip filler",
        "brazilian butt lift", "gynecomastia surgery", "nose job",
        "cosmetic botox",
    ],
    "Beauty Treatment": [
        "hydrafacial", "hydro facial", "facial treatment", "spa treatment",
        "massage", "microdermabrasion", "chemical peel", "body scrub",
        "manicure", "pedicure", "waxing", "laser hair removal",
        "teeth whitening", "sauna", "body contouring", "skin polishing",
        "facial spa", "beauty treatment",
    ],
    "Nutritional Food Supplements": [
        "multivitamin", "multi-vitamin", "multi vitamin", "probiotic",
        "probiotics", "omega 3", "omega-3", "fish oil", "glucosamine",
        "calcium supplement", "vitamin c tablet", "vitamin d supplement",
        "protein powder", "whey protein", "iron supplement",
        "zinc supplement", "biotin", "collagen supplement", "centrum",
        "seven seas", "solgar", "nature's bounty", "blackmores", "swisse",
        "food supplement", "nutritional supplement", "appetite stimulant",
    ],
    "Herbal Treatment": [
        "herbal", "ayurvedic", "homeopathic", "herbion", "herbigor",
        "echinacea", "ginseng", "ginkgo biloba", "traditional medicine",
        "unani", "chinese herbal medicine", "herbal tea", "herbal remedy",
        "herbal supplement", "herbal syrup",
    ],
    "Contact Lenses & Laser Eye Treatment": [
        "contact lens", "contact lenses", "lasik", "laser eye surgery",
        "refractive surgery", "prk", "photorefractive keratectomy",
        "lens solution", "colored contact lens", "coloured contact lens",
    ],
    "Hormone Replacement Therapy": [
        "hormone replacement therapy", "hrt", "progynova", "premarin",
        "divigel", "estraderm", "climara", "duphaston", "femoston",
        "estradiol", "estrogen therapy", "testosterone replacement therapy",
        "menopause hormone therapy",
    ],
    "Orthodontics": [
        "orthodontic", "braces", "invisalign", "dental braces",
        "orthodontic retainer", "orthodontic treatment", "teeth alignment",
        "clear aligner",
    ],
    "Epidemics & Pandemics": [
        "covid-19", "covid19", "covid 19", "coronavirus", "sars-cov-2",
        "sars cov 2", "ebola", "pandemic", "epidemic", "monkeypox", "mpox",
        "h1n1", "swine flu", "avian flu", "bird flu", "zika virus",
        "marburg", "cholera outbreak", "plague outbreak",
    ],
}


@dataclass
class RuleConfig:
    # --- §5.1 Duplicates ---
    duplicate_day_window: int = 5
    duplicate_similarity_threshold: float = 0.72
    duplicate_eligible_item_statuses: List[str] = field(
        default_factory=lambda: ["Approved"]
    )

    # --- §5.2 Non-payable ---
    non_payable_keywords: Dict[str, List[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in
                                  DEFAULT_NON_PAYABLE_KEYWORDS.items()}
    )
    non_payable_eligible_item_statuses: List[str] = field(
        default_factory=lambda: ["Approved"]
    )

    # --- §5.3 Pricing anomalies ---
    # Per-category override, falls back to default_multiplier if a category
    # isn't listed (some categories legitimately have wider price variance).
    iqr_multiplier_default: float = 1.5
    iqr_multiplier_by_category: Dict[str, float] = field(default_factory=dict)

    # --- §5.4 Invalid member/policy ---
    # Regex per payer; falls back to `default` if payer not listed.
    # Default shape: PREFIX/YY/CODE/000000/00
    policy_regex_by_payer: Dict[str, str] = field(
        default_factory=lambda: {
            "default": (
                r"^[A-Za-z]+/\d{2}/[A-Za-z0-9]+/\d{6}/\d{2}$"
            )
        }
    )


DEFAULT_CONFIG = RuleConfig()
