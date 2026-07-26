"""Migrate the legacy seen_jobs.json so previously reviewed listings do not resurface.

The old pipeline stored IDs as "reed:57030691". Same format used here, so this is a
straight import into jobs with a marker title.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import select  # noqa: E402

from app.db import create_tables, session_scope  # noqa: E402
from app.models import Job  # noqa: E402

LEGACY = Path(__file__).resolve().parent.parent.parent / "Job Alerts Automation" / "seen_jobs.json"


def main() -> None:
    create_tables()
    if not LEGACY.exists():
        print(f"No legacy file at {LEGACY}")
        return

    data = json.loads(LEGACY.read_text(encoding="utf-8"))
    ids = data.get("seen_job_ids", [])
    print(f"Found {len(ids)} legacy IDs")

    added = 0
    with session_scope() as session:
        existing = {
            f"{s}:{e}" for s, e in session.exec(select(Job.source, Job.external_id)).all()
        }
        for key in ids:
            if ":" not in key or key in existing:
                continue
            source, external_id = key.split(":", 1)
            session.add(Job(
                source=source,
                external_id=external_id,
                title="(imported from legacy pipeline)",
                company="(legacy)",
                apply_url="",
                match_score=0,
            ))
            existing.add(key)
            added += 1

    print(f"Imported {added} IDs. These will now be skipped on every pull.")


if __name__ == "__main__":
    main()
