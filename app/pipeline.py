"""Daily run: pull, dedupe, score, then tailor only what clears the threshold."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from rapidfuzz import fuzz
from sqlmodel import select

from app import config, generate
from app.db import session_scope
from app.models import Application, CVVariant, DailyStats, Job, Source
from app.sources.adzuna import AdzunaAdapter
from app.sources.ats import AshbyAdapter, GreenhouseAdapter, LeverAdapter, WorkableAdapter
from app.sources.linkedin_apify import LinkedInApifyAdapter
from app.sources.reed import ReedAdapter
from app.scoring import score_job

ADAPTERS = {
    "reed": ReedAdapter,
    "adzuna": AdzunaAdapter,
    "linkedin": LinkedInApifyAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
    "workable": WorkableAdapter,
}

SEARCH_TITLES = [
    "graduate mechanical engineer",
    "junior design engineer",
    "validation engineer",
    "test engineer",
    "manufacturing engineer",
    "quality engineer",
    "NPI engineer",
]


def _is_duplicate(job, existing: list[tuple[str, str, str]]) -> bool:
    """Catch the same role reposted by an agency under a different ID."""
    for company, title, location in existing:
        if fuzz.ratio(job.title.lower(), title.lower()) > 88 and (
            fuzz.ratio(job.company.lower(), company.lower()) > 80
            or fuzz.ratio((job.location or "").lower(), (location or "").lower()) > 85
        ):
            return True
    return False


def collect(session) -> tuple[list, dict]:
    """Run every active source. Returns (new jobs, per-source report)."""
    sources = session.exec(select(Source).where(Source.active == True)).all()  # noqa: E712
    seen_keys = {
        f"{s}:{e}" for s, e in session.exec(select(Job.source, Job.external_id)).all()
    }
    seen_shapes = session.exec(select(Job.company, Job.title, Job.location)).all()

    report: dict = {}
    collected: list = []
    apify_cost = 0.0

    for source in sources:
        adapter_cls = ADAPTERS.get(source.source_type)
        if not adapter_cls:
            continue
        adapter = adapter_cls()
        if not getattr(adapter, "enabled", True):
            report[source.source_type] = {"skipped": "not configured"}
            continue

        cfg = dict(source.config or {})
        if source.source_type == "linkedin":
            cfg["skip_ids"] = [
                k.split(":", 1)[1] for k in seen_keys if k.startswith("linkedin:")
            ][:500]

        jobs, error = adapter.run(**cfg)
        apify_cost += getattr(adapter, "last_cost", 0.0)

        fresh = []
        for job in jobs:
            if job.key() in seen_keys:
                continue
            if _is_duplicate(job, seen_shapes):
                continue
            seen_keys.add(job.key())
            seen_shapes.append((job.company, job.title, job.location))
            fresh.append(job)

        collected.extend(fresh)
        source.last_pulled = datetime.utcnow()
        source.last_error = error
        session.add(source)
        report[source.source_type] = {
            "pulled": len(jobs), "new": len(fresh), "error": error
        }

    return collected, {"sources": report, "apify_cost": round(apify_cost, 4)}


def ingest(tailor: bool = True) -> dict:
    """The whole daily job. Safe to call from a scheduler or the API."""
    with session_scope() as session:
        variants = session.exec(
            select(CVVariant).where(CVVariant.active == True)  # noqa: E712
        ).all()
        if not variants:
            return {"error": "no CV variants loaded, run scripts/init_db.py first"}

        cv_corpus = "\n".join(v.full_text for v in variants)
        master = config.MASTER_PROFILE.read_text(encoding="utf-8") if config.MASTER_PROFILE.exists() else ""

        raw_jobs, report = collect(session)

        # Score everything offline, cheapest step first.
        scored = []
        for raw in raw_jobs:
            data = raw.as_dict()
            result = score_job(data, cv_corpus)
            job = Job(
                **{k: v for k, v in data.items() if k in Job.model_fields},
                match_score=result["score"],
                score_breakdown=result["breakdown"],
                red_flags=result["red_flags"],
            )
            session.add(job)
            scored.append(job)

        session.flush()
        scored.sort(key=lambda j: j.match_score or 0, reverse=True)

        qualified = [
            j for j in scored
            if (j.match_score or 0) >= config.MATCH_THRESHOLD
        ][:config.DAILY_JOB_CAP]

        llm_cost = 0.0
        generated = 0
        if tailor:
            for job in qualified:
                try:
                    package = generate.tailor(
                        {
                            "title": job.title, "company": job.company,
                            "location": job.location, "description": job.description,
                        },
                        variants, master,
                    )
                except Exception as exc:
                    session.add(Application(
                        job_id=job.id, status="pending", flagged=True,
                        flag_reasons=[f"generation error: {exc}"],
                    ))
                    continue

                if package.get("error"):
                    session.add(Application(
                        job_id=job.id, status="pending", flagged=True,
                        flag_reasons=package.get("flag_reasons", ["generation failed"]),
                    ))
                    continue

                llm_cost += package.pop("llm_cost_usd", 0.0)
                variant = next((v for v in variants if v.id == package["cv_variant_id"]), None)

                out_path = None
                if variant:
                    safe = "".join(c for c in f"{job.company}_{job.title}" if c.isalnum() or c in " _-")[:60]
                    out_path = Path(config.OUTPUT_DIR) / f"{safe}.docx"
                    try:
                        generate.write_cv(variant.file_path, package, out_path)
                    except Exception as exc:
                        package.setdefault("flag_reasons", []).append(f"docx write failed: {exc}")
                        package["flagged"] = True
                        out_path = None

                session.add(Application(
                    job_id=job.id,
                    generated_cv_path=str(out_path) if out_path else None,
                    **{k: v for k, v in package.items() if k in Application.model_fields},
                ))
                generated += 1

        today = date.today()
        stats = session.get(DailyStats, today) or DailyStats(date=today)
        stats.jobs_pulled = (stats.jobs_pulled or 0) + len(scored)
        stats.jobs_qualified = (stats.jobs_qualified or 0) + len(qualified)
        stats.llm_cost_usd = round((stats.llm_cost_usd or 0) + llm_cost, 4)
        stats.apify_cost_usd = round((stats.apify_cost_usd or 0) + report["apify_cost"], 4)
        session.add(stats)

        return {
            "pulled": len(scored),
            "qualified": len(qualified),
            "generated": generated,
            "llm_cost_usd": round(llm_cost, 4),
            "apify_cost_usd": report["apify_cost"],
            "sources": report["sources"],
        }
