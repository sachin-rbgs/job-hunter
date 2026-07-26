"""Common job shape and adapter registry."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

import httpx

TIMEOUT = httpx.Timeout(30.0)

# Rough drive distances from Loughborough (LE11), for commute scoring without a
# geocoding API. Anything unlisted falls back to None, which scores neutral.
DISTANCES = {
    "loughborough": 0, "leicester": 12, "nottingham": 16, "derby": 18,
    "coventry": 35, "birmingham": 40, "burton": 20, "burton-on-trent": 20,
    "burton upon trent": 20, "tamworth": 28, "hinckley": 18, "rugby": 33,
    "northampton": 45, "sheffield": 55, "milton keynes": 60, "peterborough": 55,
    "warwick": 40, "solihull": 38, "wolverhampton": 50, "stoke": 45,
    "lichfield": 30, "market harborough": 22, "corby": 35, "kettering": 40,
    "mansfield": 30, "chesterfield": 40, "worcester": 60, "telford": 65,
    "london": 110, "bristol": 130, "manchester": 80, "leeds": 80,
    "cambridge": 85, "oxford": 85, "reading": 105, "swindon": 100,
}

REMOTE_RE = re.compile(r"\b(fully remote|remote first|work from home|wfh)\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)


@dataclass
class RawJob:
    source: str
    external_id: str
    title: str
    company: str
    apply_url: str
    location: Optional[str] = None
    description: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    exp_level: Optional[str] = None
    ats_type: Optional[str] = None
    questions_json: Optional[list] = None
    posted_at: Optional[datetime] = None
    remote: Optional[str] = None
    commute_miles: Optional[float] = None

    def key(self) -> str:
        return f"{self.source}:{self.external_id}"

    def as_dict(self) -> dict:
        return asdict(self)


def infer_remote(text: str) -> Optional[str]:
    if not text:
        return None
    if REMOTE_RE.search(text):
        return "remote"
    if HYBRID_RE.search(text):
        return "hybrid"
    return "onsite"


def estimate_commute(location: str | None) -> Optional[float]:
    if not location:
        return None
    low = location.lower()
    for town, miles in DISTANCES.items():
        if town in low:
            return float(miles)
    return None


def enrich(job: RawJob) -> RawJob:
    blob = f"{job.title} {job.location or ''} {job.description or ''}"
    job.remote = job.remote or infer_remote(blob)
    if job.commute_miles is None:
        job.commute_miles = estimate_commute(job.location)
    return job


class Adapter:
    """Subclasses implement fetch() and return a list of RawJob."""

    source = "base"
    enabled = True

    def fetch(self, **kwargs) -> list[RawJob]:
        raise NotImplementedError

    def run(self, **kwargs) -> tuple[list[RawJob], Optional[str]]:
        try:
            jobs = [enrich(j) for j in self.fetch(**kwargs)]
            return jobs, None
        except Exception as exc:  # adapters must never take the pipeline down
            return [], f"{type(exc).__name__}: {exc}"
