"""FastAPI app: review queue API plus the static UI."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app import config, pipeline
from app.db import create_tables, get_session
from app.models import Application, CVVariant, DailyStats, Job

app = FastAPI(title="Job Hunter", version="1.0")

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.on_event("startup")
def _startup() -> None:
    create_tables()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/queue")
def queue(status: str = "pending", limit: int = 100,
          session: Session = Depends(get_session)) -> list[dict]:
    """Review queue, best match first."""
    stmt = select(Application, Job).join(Job, Application.job_id == Job.id)
    if status != "all":
        stmt = stmt.where(Application.status == status)
    stmt = stmt.order_by(Job.match_score.desc()).limit(limit)

    out = []
    for application, job in session.exec(stmt).all():
        out.append({
            "id": application.id,
            "job": {
                "id": job.id,
                "key": job.job_key,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "commute_miles": job.commute_miles,
                "remote": job.remote,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "match_score": job.match_score,
                "score_breakdown": job.score_breakdown,
                "red_flags": job.red_flags,
                "apply_url": job.apply_url,
                "ats_type": job.ats_type,
                "questions": job.questions_json,
                "posted_at": job.posted_at,
            },
            "cv_variant": application.cv_variant_name,
            "cv_reasoning": application.cv_reasoning,
            "bullet_edits": application.bullet_edits,
            "added_skills": application.added_skills,
            "missing_keywords": application.missing_keywords,
            "cover_letter": application.cover_letter,
            "key_skill_matches": application.key_skill_matches,
            "skills_gap": application.skills_gap,
            "match_rationale": application.match_rationale,
            "alignment_before": application.alignment_before,
            "alignment_after": application.alignment_after,
            "flagged": application.flagged,
            "flag_reasons": application.flag_reasons,
            "has_cv": bool(application.generated_cv_path),
            "status": application.status,
        })
    return out


@app.post("/api/applications/{app_id}/status")
def set_status(app_id: int, payload: dict,
               session: Session = Depends(get_session)) -> dict:
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "not found")

    status = payload.get("status", "pending")
    if status not in {"pending", "sent", "skipped", "heard_back", "interview", "offer", "rejected"}:
        raise HTTPException(400, "bad status")

    application.status = status
    application.skip_reason = payload.get("skip_reason")
    if status == "sent":
        application.sent_at = datetime.utcnow()
        today = date.today()
        stats = session.get(DailyStats, today) or DailyStats(date=today)
        stats.apps_sent = (stats.apps_sent or 0) + 1
        session.add(stats)

    session.add(application)
    session.commit()
    return {"ok": True, "status": status}


@app.post("/api/applications/{app_id}/cover_letter")
def edit_cover_letter(app_id: int, payload: dict,
                      session: Session = Depends(get_session)) -> dict:
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "not found")
    application.cover_letter = payload.get("cover_letter", "")
    session.add(application)
    session.commit()
    return {"ok": True}


@app.get("/api/applications/{app_id}/cv")
def download_cv(app_id: int, session: Session = Depends(get_session)):
    application = session.get(Application, app_id)
    if not application or not application.generated_cv_path:
        raise HTTPException(404, "no generated CV")
    path = Path(application.generated_cv_path)
    if not path.exists():
        raise HTTPException(404, "file missing")
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )


@app.get("/api/stats")
def stats(session: Session = Depends(get_session)) -> dict:
    rows = session.exec(select(DailyStats).order_by(DailyStats.date.desc()).limit(30)).all()
    applications = session.exec(select(Application)).all()

    by_variant: dict[str, dict] = {}
    for a in applications:
        if not a.cv_variant_name:
            continue
        bucket = by_variant.setdefault(a.cv_variant_name, {"sent": 0, "replies": 0})
        if a.status in {"sent", "heard_back", "interview", "offer", "rejected"}:
            bucket["sent"] += 1
        if a.status in {"heard_back", "interview", "offer"}:
            bucket["replies"] += 1

    return {
        "daily": [r.model_dump() for r in rows],
        "totals": {
            "pending": sum(1 for a in applications if a.status == "pending"),
            "sent": sum(1 for a in applications if a.status == "sent"),
            "flagged": sum(1 for a in applications if a.flagged),
        },
        "by_variant": by_variant,
        "cost_to_date": round(
            sum((r.llm_cost_usd or 0) + (r.apify_cost_usd or 0) for r in rows), 2
        ),
    }


@app.get("/api/variants")
def variants(session: Session = Depends(get_session)) -> list[dict]:
    return [
        {"id": v.id, "name": v.name, "tags": v.lean_tags,
         "bullets": len(v.bullets or []), "active": v.active}
        for v in session.exec(select(CVVariant)).all()
    ]


@app.post("/api/ingest")
def run_ingest(tailor: bool = True) -> dict:
    """Called by the scheduler, or by hand from the UI."""
    return pipeline.ingest(tailor=tailor)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "llm": bool(config.ANTHROPIC_API_KEY),
        "reed": bool(config.REED_API_KEY),
        "adzuna": bool(config.ADZUNA_APP_ID),
        "linkedin": bool(config.APIFY_TOKEN),
        "alignment_target": config.ALIGNMENT_TARGET,
    }
