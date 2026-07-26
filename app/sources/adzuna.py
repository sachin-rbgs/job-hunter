"""Adzuna UK. Free tier is roughly 1,000 calls a month, so budget a handful a day."""
from __future__ import annotations

from datetime import datetime

import httpx

from app import config
from app.sources.base import TIMEOUT, Adapter, RawJob

BASE = "https://api.adzuna.com/v1/api/jobs/gb/search/{page}"


class AdzunaAdapter(Adapter):
    source = "adzuna"

    def __init__(self):
        self.enabled = bool(config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY)

    def fetch(self, keywords: str = "graduate mechanical engineer",
              location: str = "Loughborough", distance: int = 50,
              limit: int = 50, page: int = 1, **_) -> list[RawJob]:
        if not self.enabled:
            return []

        params = {
            "app_id": config.ADZUNA_APP_ID,
            "app_key": config.ADZUNA_APP_KEY,
            "what": keywords,
            "where": location,
            "distance": distance,
            "results_per_page": min(limit, 50),
            "max_days_old": 2,
            "content-type": "application/json",
        }
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(BASE.format(page=page), params=params)
            resp.raise_for_status()
            payload = resp.json()

        jobs = []
        for item in payload.get("results", []):
            posted = None
            if item.get("created"):
                try:
                    posted = datetime.fromisoformat(item["created"].replace("Z", "+00:00"))
                except ValueError:
                    pass
            jobs.append(RawJob(
                source=self.source,
                external_id=str(item.get("id")),
                title=item.get("title", ""),
                company=(item.get("company") or {}).get("display_name", ""),
                location=(item.get("location") or {}).get("display_name"),
                description=item.get("description", ""),
                salary_min=int(item["salary_min"]) if item.get("salary_min") else None,
                salary_max=int(item["salary_max"]) if item.get("salary_max") else None,
                apply_url=item.get("redirect_url", ""),
                posted_at=posted,
            ))
        return jobs
