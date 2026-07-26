"""Anti-fabrication checks.

Everything generated must trace back to the chosen CV variant or the master skills
profile. This module catches the failure modes that matter on a real application:
invented employers, invented dates, invented credentials, and invented numbers.
"""
from __future__ import annotations

import re

# Credentials worth guarding. If generated text claims one, the source must contain it.
CREDENTIALS = [
    "cswp", "certified solidworks professional", "ceng", "ieng", "imeche", "pmp",
    "six sigma black belt", "black belt", "green belt", "nebosh", "prince2",
    "chartered", "phd", "msc", "meng", "beng", "mba", "hnd", "hnc",
    "iso 17025", "iatf 16949", "iso 9001", "matlab onramp",
]

YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")
# "12%", "3x", "doubled", "reduced by 40"
METRIC_RE = re.compile(r"\b(\d+(?:\.\d+)?\s*(?:%|percent|x\b))", re.I)
COMPANY_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,3})\s+"
    r"(Ltd|Limited|PLC|Plc|Inc|LLC|GmbH|Group|Corporation|Corp)\b")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def check(generated: str, sources: list[str], allow_company: str | None = None) -> list[str]:
    """Return a list of fabrication concerns. Empty list means clean.

    `sources` should be [chosen_cv_text, master_profile_text].
    `allow_company` is the employer being applied to, which will legitimately appear
    in a cover letter without being in the CV.
    """
    issues: list[str] = []
    if not generated:
        return issues

    corpus = _norm(" \n ".join(s for s in sources if s))
    gen_norm = _norm(generated)
    allowed = _norm(allow_company or "")

    # 1. Credentials
    for cred in CREDENTIALS:
        if cred in gen_norm and cred not in corpus:
            issues.append(f"claims credential not in source: '{cred}'")

    # 2. Years and dates
    for year in set(YEAR_RE.findall(generated)):
        if year not in corpus:
            issues.append(f"cites year not in source: {year}")

    # 3. Quantified metrics
    for metric in set(m.strip() for m in METRIC_RE.findall(generated)):
        if _norm(metric) not in corpus:
            issues.append(f"cites metric not in source: '{metric}'")

    # 4. Employer-shaped names
    for match in COMPANY_SUFFIX_RE.finditer(generated):
        name = _norm(match.group(1))
        if name and name not in corpus and name not in allowed:
            issues.append(f"names an organisation not in source: '{match.group(1)}'")

    return sorted(set(issues))


def verify_skill_additions(additions: list[str], master_profile: str) -> tuple[list[str], list[str]]:
    """Split proposed skill additions into (honest, rejected).

    A skill may only be added to a CV if the master profile already claims it.
    This is the mechanism that raises alignment without inventing anything.
    """
    corpus = _norm(master_profile)
    honest, rejected = [], []
    for skill in additions or []:
        if _norm(skill) and _norm(skill) in corpus:
            honest.append(skill)
        else:
            rejected.append(skill)
    return honest, rejected


def verify_bullet_edit(original: str, revised: str, sources: list[str]) -> list[str]:
    """A rewritten bullet may re-emphasise but not add new factual claims."""
    issues = check(revised, sources)
    corpus = _norm(" ".join(sources))

    # Any capitalised tool/standard token in the revision should already exist somewhere.
    tokens = re.findall(r"\b[A-Z][A-Za-z0-9&\-]{2,}\b", revised)
    for token in set(tokens):
        low = _norm(token)
        if low in {"the", "and", "for", "with", "led", "designed", "improved"}:
            continue
        if low not in corpus:
            issues.append(f"introduces unsourced term: '{token}'")
    return sorted(set(issues))
