"""LinkedIn via the Apify actor valig/linkedin-jobs-scraper.

Chosen over bebity because it is pay-per-result (about $0.0004 a job, so roughly
60p a month at 50 jobs a day) rather than $29.99 flat, and because it accepts
`skipJobId`, which means already-seen IDs are filtered server side before you are
charged for them.

Two things to keep in mind. First, this is a third-party scraper, so it keeps the
user's own LinkedIn account out of the loop entirely, but it does not make the
activity permitted under LinkedIn's User Agreement. Keep volume personal-scale and
do not republish the data. Second, actors get deprecated. This adapter is behind the
same interface as every other source and can be switched off in config without
touching anything else.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from app import config
from app.sources.base import Adapter, RawJob

ACTOR = "valig~linkedin-jobs-scraper"
ENDPOINT = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"

EXPERIENCE_INTERNSHIP = "1"
EXPERIENCE_ENTRY = "2"
EXPERIENCE_ASSOCIATE = "3"


class LinkedInApifyAdapter(Adapter):
    source = "linkedin"

    def __init__(self):
        self.enabled = bool(config.APIFY_TOKEN)
        self.last_cost = 0.0

    def fetch(self, title: str = "graduate mechanical engineer",
              location: str = "United Kingdom",
              date_posted: str = "r86400",
              limit: int = 50,
              skip_ids: list[str] | None = None,
              **_) -> list[RawJob]:
        if not self.enabled:
            return []

        payload = {
            "title": title,
            "location": location,
            "datePosted": date_posted,  # r86400 = last 24h, r604800 = last week
            "experienceLevel": [EXPERIENCE_INTERNSHIP, EXPERIENCE_ENTRY, EXPERIENCE_ASSOCIATE],
            "contractType": ["F"],
            "limit": limit,
        }
        if skip_ids:
            payload["skipJobId"] = skip_ids

        with httpx.Client(timeout=httpx.Timeout(300.0)) as client:
            resp = client.post(
                ENDPOINT,
                params={"token": config.APIFY_TOKEN},
                json=payload,
            )
            resp.raise_for_status()
            items = resp.json()

        self.last_cost = (
            len(items) * config.APIFY_COST_PER_RESULT + config.APIFY_COST_PER_START
        )

        jobs = []
        for item in items:
            posted = None
            raw_date = item.get("postedAt") or item.get("publishedAt")
            if raw_date:
                try:
                    posted = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
                except ValueError:
                    pass

            salary_min = salary_max = None
            comp = item.get("salary") or {}
            if isinstance(comp, dict):
                salary_min = comp.get("min")
                salary_max = comp.get("max")

            jobs.append(RawJob(
                source=self.source,
                external_id=str(item.get("id") or item.get("jobId") or item.get("url", "")),
                title=item.get("title", ""),
                company=item.get("companyName") or item.get("company", ""),
                location=item.get("location"),
                description=item.get("descriptionText") or item.get("description", ""),
                exp_level=item.get("experienceLevel"),
                salary_min=int(salary_min) if salary_min else None,
                salary_max=int(salary_max) if salary_max else None,
                apply_url=item.get("url") or item.get("jobUrl", ""),
                ats_type="linkedin",
                posted_at=posted,
            ))
        return jobs
