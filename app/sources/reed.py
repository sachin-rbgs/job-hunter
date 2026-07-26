"""Reed.co.uk Jobseeker API. Free key from reed.co.uk/developers.

Auth is HTTP Basic with the API key as the username and an empty password.
"""
from __future__ import annotations

import base64
from datetime import datetime

import httpx

from app import config
from app.sources.base import TIMEOUT, Adapter, RawJob

BASE = "https://www.reed.co.uk/api/1.0/search"


class ReedAdapter(Adapter):
    source = "reed"

    def __init__(self):
        self.enabled = bool(config.REED_API_KEY)

    def _headers(self) -> dict:
        token = base64.b64encode(f"{config.REED_API_KEY}:".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def fetch(self, keywords: str = "graduate mechanical engineer",
              location: str = "Loughborough", distance: int = 50,
              limit: int = 50, **_) -> list[RawJob]:
        if not self.enabled:
            return []

        params = {
            "keywords": keywords,
            "locationName": location,
            "distanceFromLocation": distance,
            "resultsToTake": limit,
            "postedByDirectEmployer": "false",
        }
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(BASE, params=params, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()

        jobs = []
        for item in payload.get("results", []):
            posted = None
            if item.get("date"):
                try:
                    posted = datetime.strptime(item["date"], "%d/%m/%Y")
                except ValueError:
                    pass
            jobs.append(RawJob(
                source=self.source,
                external_id=str(item.get("jobId")),
                title=item.get("jobTitle", ""),
                company=item.get("employerName", ""),
                location=item.get("locationName"),
                description=item.get("jobDescription", ""),
                salary_min=int(item["minimumSalary"]) if item.get("minimumSalary") else None,
                salary_max=int(item["maximumSalary"]) if item.get("maximumSalary") else None,
                apply_url=item.get("jobUrl", ""),
                posted_at=posted,
            ))
        return jobs
