"""Company ATS boards: Greenhouse, Lever, Ashby, Workable.

All unauthenticated, no rate limits worth worrying about, and they return the full
job description. Best signal-to-noise of any source here, and free. The Greenhouse
adapter also pulls the posting's custom questions so answers can be pre-drafted
before the form is ever opened.
"""
from __future__ import annotations

import re
from datetime import datetime

import httpx

from app.sources.base import TIMEOUT, Adapter, RawJob

TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    return TAG_RE.sub("", text).replace("&amp;", "&").replace("&nbsp;", " ").strip()


class GreenhouseAdapter(Adapter):
    source = "greenhouse"

    def fetch(self, board_token: str = "", **_) -> list[RawJob]:
        if not board_token:
            return []
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()

        jobs = []
        for item in payload.get("jobs", []):
            posted = None
            if item.get("updated_at"):
                try:
                    posted = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                except ValueError:
                    pass
            jobs.append(RawJob(
                source=self.source,
                external_id=str(item.get("id")),
                title=item.get("title", ""),
                company=board_token,
                location=(item.get("location") or {}).get("name"),
                description=strip_html(item.get("content", "")),
                apply_url=item.get("absolute_url", ""),
                ats_type="greenhouse",
                questions_json=item.get("questions"),
                posted_at=posted,
            ))
        return jobs


class LeverAdapter(Adapter):
    source = "lever"

    def fetch(self, company: str = "", **_) -> list[RawJob]:
        if not company:
            return []
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()

        jobs = []
        for item in payload:
            posted = None
            if item.get("createdAt"):
                try:
                    posted = datetime.fromtimestamp(item["createdAt"] / 1000)
                except (ValueError, OSError):
                    pass
            categories = item.get("categories") or {}
            jobs.append(RawJob(
                source=self.source,
                external_id=str(item.get("id")),
                title=item.get("text", ""),
                company=company,
                location=categories.get("location"),
                description=strip_html(item.get("descriptionPlain") or item.get("description", "")),
                apply_url=item.get("hostedUrl", ""),
                ats_type="lever",
                posted_at=posted,
            ))
        return jobs


class AshbyAdapter(Adapter):
    source = "ashby"

    def fetch(self, company: str = "", **_) -> list[RawJob]:
        if not company:
            return []
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()

        jobs = []
        for item in payload.get("jobs", []):
            jobs.append(RawJob(
                source=self.source,
                external_id=str(item.get("id")),
                title=item.get("title", ""),
                company=company,
                location=item.get("location"),
                description=strip_html(item.get("descriptionPlain") or item.get("descriptionHtml", "")),
                apply_url=item.get("applyUrl") or item.get("jobUrl", ""),
                ats_type="ashby",
            ))
        return jobs


class WorkableAdapter(Adapter):
    source = "workable"

    def fetch(self, company: str = "", **_) -> list[RawJob]:
        if not company:
            return []
        url = f"https://apply.workable.com/api/v1/widget/accounts/{company}"
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()

        jobs = []
        for item in payload.get("jobs", []):
            loc = ", ".join(filter(None, [item.get("city"), item.get("country")]))
            jobs.append(RawJob(
                source=self.source,
                external_id=str(item.get("shortcode") or item.get("id")),
                title=item.get("title", ""),
                company=payload.get("name", company),
                location=loc or None,
                description=strip_html(item.get("description", "")),
                apply_url=item.get("url") or item.get("application_url", ""),
                ats_type="workable",
            ))
        return jobs
