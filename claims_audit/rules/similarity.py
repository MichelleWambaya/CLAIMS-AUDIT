"""
Product-name similarity, ported exactly from the prototype.

Uses the MAX of:
  - normalized character similarity (Levenshtein ratio), which catches
    near-identical strings with small typos/casing/punctuation differences
  - token-overlap (Jaccard on whitespace-split tokens), which catches
    reordered / abbreviated names that a pure character metric misses
    (e.g. "Panadol Extra 500mg Tablets" vs "Panadol Extra Tablets 500mg" —
    identical tokens, different order, so Levenshtein alone scores this
    much lower than it deserves)

Known limitation (surface this in the UI next to any flagged pair):
this is a heuristic. It can flag genuinely different items that happen to
share several words (e.g. two different scan modalities for the same body
part), and it can miss oddly-reordered near-duplicates that share no tokens
at all. Always show the score, never auto-dismiss based on it alone.
"""
import re


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) == 0:
        return len(b)
    if len(b) == 0:
        return len(a)

    prev_row = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur_row = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur_row[j] = min(
                prev_row[j] + 1,      # deletion
                cur_row[j - 1] + 1,   # insertion
                prev_row[j - 1] + cost,  # substitution
            )
        prev_row = cur_row
    return prev_row[-1]


def levenshtein_ratio(a: str, b: str) -> float:
    """Normalized character similarity in [0, 1]. 1.0 == identical."""
    a, b = _normalize(a), _normalize(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    dist = _levenshtein_distance(a, b)
    max_len = max(len(a), len(b))
    return 1.0 - (dist / max_len)


def jaccard_token_similarity(a: str, b: str) -> float:
    """Token-overlap similarity in [0, 1]."""
    ta = set(_normalize(a).split())
    tb = set(_normalize(b).split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    intersection = ta & tb
    union = ta | tb
    return len(intersection) / len(union)


def hybrid_similarity(a: str, b: str) -> float:
    """Max of character-level and token-level similarity, per the prototype."""
    return max(levenshtein_ratio(a, b), jaccard_token_similarity(a, b))
