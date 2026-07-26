"""First run: create tables, load CV variants, seed sources.

Safe to re-run. Re-reads the .docx files, so run it again after editing a CV.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import select  # noqa: E402

from app import config  # noqa: E402
from app.cv import loader  # noqa: E402
from app.db import create_tables, session_scope  # noqa: E402
from app.models import CVVariant, Source  # noqa: E402

# The CV folder sits one level up from this project.
CV_ROOT = Path(__file__).resolve().parent.parent.parent

# Seed ATS boards. Add UK engineering employers here as you find their tokens.
# Verify a token first: https://boards-api.greenhouse.io/v1/boards/<token>/jobs
ATS_SEEDS = [
    ("greenhouse", {"board_token": "dyson"}),
    ("lever", {"company": "ricardo"}),
    ("ashby", {"company": "monumental"}),
]

SEARCHES = [
    "graduate mechanical engineer",
    "junior design engineer",
    "validation engineer",
    "manufacturing engineer",
    "quality engineer",
]


def main() -> None:
    create_tables()
    print(f"CV root: {CV_ROOT}")

    master = loader.load_master_profile(CV_ROOT)
    print(f"master profile: {len(master)} chars"
          if master else "  WARNING: MASTER_SKILLS_PROFILE.md not found")

    variants = loader.discover(CV_ROOT)
    if not variants:
        print("  ERROR: no CV variants found. Check folder names in app/cv/loader.py")
        return

    with session_scope() as session:
        for found in variants:
            existing = session.exec(
                select(CVVariant).where(CVVariant.name == found.name)
            ).first()
            record = existing or CVVariant(name=found.name)
            record.file_path = found.file_path
            record.full_text = found.full_text
            record.bullets = found.bullets
            record.lean_tags = found.lean_tags
            record.active = True
            session.add(record)
            print(f"  {found.name:18} {len(found.bullets):3} bullets  "
                  f"{len(found.full_text):5} chars")

        # Reed and Adzuna: one source row per search term.
        for term in SEARCHES:
            for kind in ("reed", "adzuna"):
                cfg = {"keywords": term, "location": config.HOME_POSTCODE,
                       "distance": config.MAX_COMMUTE_MILES}
                exists = session.exec(
                    select(Source).where(Source.source_type == kind)
                ).all()
                if any((s.config or {}).get("keywords") == term for s in exists):
                    continue
                session.add(Source(source_type=kind, config=cfg))

        # LinkedIn via Apify, one row per search title.
        for term in SEARCHES:
            exists = session.exec(
                select(Source).where(Source.source_type == "linkedin")
            ).all()
            if any((s.config or {}).get("title") == term for s in exists):
                continue
            session.add(Source(
                source_type="linkedin",
                config={"title": term, "location": "United Kingdom",
                        "date_posted": "r86400", "limit": 25},
                active=bool(config.APIFY_TOKEN),
            ))

        for kind, cfg in ATS_SEEDS:
            key = cfg.get("board_token") or cfg.get("company")
            exists = session.exec(
                select(Source).where(Source.source_type == kind)
            ).all()
            if any((s.config or {}).get("board_token") == key
                   or (s.config or {}).get("company") == key for s in exists):
                continue
            session.add(Source(source_type=kind, config=cfg))

    print("\nDone. Next:")
    print("  python scripts/import_seen_jobs.py   # skip jobs you already reviewed")
    print("  python scripts/run_ingest.py         # first pull")
    print("  uvicorn app.main:app --reload        # http://localhost:8000")


if __name__ == "__main__":
    main()
