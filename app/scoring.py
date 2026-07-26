"""Match scoring, UK red flags, and ATS alignment.

Runs entirely offline before any LLM call, so we never pay to tailor a job that
was never worth applying to.
"""
from __future__ import annotations

import re

from app import config

# --- skill vocabulary ------------------------------------------------------
# Tier 1 carries most weight: things the CV can evidence with real depth.
TIER1 = {
    "solidworks", "ansys", "comsol", "autocad", "catia", "creo", "siemens nx", "inventor",
    "fea", "finite element", "cfd", "gd&t", "gdt", "geometric dimensioning",
    "dfmea", "pfmea", "fmea", "rcca", "root cause", "8d",
    "minitab", "spc", "statistical process control", "six sigma", "lean",
    "iso 17025", "iatf 16949", "iso 9001", "matlab", "python", "vba",
    "tolerance stack", "design for manufacture", "dfm", "dfa",
    "vibration testing", "thermal", "environmental testing", "validation", "verification",
    "test rig", "instrumentation", "calibration", "teamcenter", "sap",
}

TIER2 = {
    "cad", "3d modelling", "3d modeling", "2d drawings", "technical drawings",
    "prototyping", "3d printing", "material selection", "stress analysis",
    "fatigue", "heat transfer", "thermodynamics", "excel", "sql", "power bi",
    "plm", "bom", "ecn", "engineering change", "capa", "qms", "apqp", "ppap",
    "continuous improvement", "kaizen", "5s", "process improvement",
    "automotive", "aerospace", "manufacturing", "product development", "npi",
}

SECTOR_TERMS = {
    "automotive", "aerospace", "motorsport", "power electronics", "electronics",
    "manufacturing", "energy", "rail", "defence", "medical device", "ev",
    "electrification", "battery", "semiconductor",
}

GRAD_TERMS = {
    "graduate", "junior", "entry level", "entry-level", "trainee", "apprentice",
    "placement", "intern", "assistant", "associate", "early career", "no experience",
}

SENIOR_TERMS = {
    "senior", "lead ", "principal", "head of", "manager", "chartered", "expert",
    "5+ years", "5 years", "7+ years", "10+ years",
}

# --- red flag patterns -----------------------------------------------------
CLEARANCE_RE = re.compile(
    r"\b(sc clearance|dv clearance|security clearance|bpss|developed vetting|"
    r"security cleared|must be sc|eligible for sc|uk eyes only)\b", re.I)

NO_SPONSOR_RE = re.compile(
    r"(no sponsorship|cannot sponsor|unable to sponsor|not able to sponsor|"
    r"sponsorship is not|without sponsorship|must have (the )?right to work|"
    r"existing right to work|no visa)", re.I)

CHARTER_RE = re.compile(r"\b(chartered engineer|ceng|ieng|working towards ceng|imeche registration)\b", re.I)

# "3+ years", "minimum of 4 years", "at least 5 years experience"
YEARS_RE = re.compile(
    r"(?:(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years?|(?:minimum|at least|min\.?)\s*(?:of\s*)?(\d+)\s*years?)"
    r"[^.]{0,40}?(?:experience|exp\b)", re.I)

AGENCY_RE = re.compile(r"\b(recruitment|recruiting|resourcing|staffing|talent solutions|agency)\b", re.I)


def extract_required_years(text: str) -> int | None:
    """Highest explicitly required years of experience found in the body text."""
    if not text:
        return None
    years = []
    for match in YEARS_RE.finditer(text):
        raw = match.group(1) or match.group(2)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 < value <= 20:
            years.append(value)
    return max(years) if years else None


def find_keywords(text: str) -> set[str]:
    """Vocabulary terms present in a block of text."""
    low = (text or "").lower()
    return {term for term in (TIER1 | TIER2) if term in low}


def ats_alignment(job_description: str, cv_text: str) -> dict:
    """How well a CV covers the skills a job actually asks for, as a percentage.

    Only counts terms the job mentions. A CV is not penalised for omitting skills
    the employer never asked about.
    """
    required = find_keywords(job_description)
    if not required:
        return {"score": 100, "matched": [], "missing": [], "required": []}

    cv_low = (cv_text or "").lower()
    matched = sorted(t for t in required if t in cv_low)
    missing = sorted(required - set(matched))

    # Tier 1 terms count double, since those are what a screener filters on.
    def weight(term: str) -> int:
        return 2 if term in TIER1 else 1

    got = sum(weight(t) for t in matched)
    total = sum(weight(t) for t in required)
    score = round(100 * got / total) if total else 100

    return {"score": score, "matched": matched, "missing": missing, "required": sorted(required)}


def detect_red_flags(job) -> list[str]:
    """UK-specific dealbreakers, checked against title + description."""
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    title_low = (job.get("title") or "").lower()
    flags: list[str] = []

    if CLEARANCE_RE.search(text) and not config.HAS_CLEARANCE:
        flags.append("security_clearance_required")

    if NO_SPONSOR_RE.search(text) and config.NEEDS_SPONSORSHIP:
        flags.append("no_sponsorship_available")

    if CHARTER_RE.search(text):
        flags.append("chartership_required")

    years = extract_required_years(text)
    if years and years > 2:
        looks_junior = any(t in title_low for t in GRAD_TERMS)
        flags.append(
            f"junior_title_but_{years}y_required" if looks_junior else f"requires_{years}y_experience"
        )

    if any(t in title_low for t in SENIOR_TERMS):
        flags.append("seniority_mismatch")

    if AGENCY_RE.search(job.get("company", "")):
        flags.append("agency_listing")

    return flags


def _experience_points(job, flags: list[str]) -> int:
    title_low = (job.get("title") or "").lower()
    if any(f.startswith("requires_") or "_but_" in f for f in flags):
        return 0
    if "seniority_mismatch" in flags:
        return 3
    if any(t in title_low for t in GRAD_TERMS):
        return 25
    years = extract_required_years(f"{job.get('title','')} {job.get('description','')}")
    if years is None:
        return 15
    return 20 if years <= 2 else 0


def _commute_points(job) -> int:
    miles = job.get("commute_miles")
    remote = (job.get("remote") or "").lower()
    if remote in {"remote", "hybrid"}:
        return 15
    if miles is None:
        return 8
    if miles <= 25:
        return 15
    if miles <= config.MAX_COMMUTE_MILES:
        return 10
    return 0


def _salary_points(job) -> int:
    low = job.get("salary_min")
    if low is None:
        return 5  # unstated is neutral, not a penalty
    return 10 if low >= config.SALARY_FLOOR else 0


def score_job(job: dict, cv_corpus: str) -> dict:
    """Score a job 0-100. `cv_corpus` is the combined text of all active CV variants."""
    flags = detect_red_flags(job)
    description = f"{job.get('title','')}\n{job.get('description','')}"

    # 1. Skill overlap, tier-weighted (35)
    required = find_keywords(description)
    corpus_low = cv_corpus.lower()
    if required:
        got = sum(2 if t in TIER1 else 1 for t in required if t in corpus_low)
        total = sum(2 if t in TIER1 else 1 for t in required)
        skill_pts = round(35 * got / total)
    else:
        skill_pts = 12

    exp_pts = _experience_points(job, flags)          # 25
    commute_pts = _commute_points(job)                 # 15
    sector_pts = 15 if any(s in description.lower() for s in SECTOR_TERMS) else 5
    salary_pts = _salary_points(job)                   # 10

    total_score = skill_pts + exp_pts + commute_pts + sector_pts + salary_pts

    # Hard zeros
    if "security_clearance_required" in flags or "no_sponsorship_available" in flags:
        total_score = 0
    if "chartership_required" in flags:
        total_score = max(0, total_score - 25)

    breakdown = {
        "skills": skill_pts,
        "experience": exp_pts,
        "commute": commute_pts,
        "sector": sector_pts,
        "salary": salary_pts,
    }
    return {
        "score": max(0, min(100, total_score)),
        "breakdown": breakdown,
        "red_flags": flags,
        "required_keywords": sorted(required),
    }
