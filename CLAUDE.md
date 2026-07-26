# Job Hunter

Daily UK job pipeline for a graduate mechanical engineer. Pulls listings, scores them,
routes each to the best existing CV variant, raises ATS alignment to ~90% using only
true skills, and drafts a cover letter. The user reviews and submits. Nothing auto-submits.

## Core rule: never fabricate

Every word that reaches a CV or cover letter must trace to a source file:
- one of the CV variants in `data/cv_variants/`
- `MASTER_SKILLS_PROFILE.md` (the superset of everything the user can honestly claim)

The master profile is deliberately larger than any single CV. That is the whole mechanism
for raising alignment: when a job asks for a skill the chosen CV omits but the master
profile contains, we surface it. We never invent employers, titles, dates, degrees,
certifications, tools, or metrics. `app/verify.py` enforces this and flags violations.

If alignment cannot reach the target honestly, report the real number. Do not close the gap.

## Architecture

```
app/
  main.py        FastAPI app + review queue API
  config.py      settings from .env
  models.py      SQLModel tables
  db.py          engine + session
  scoring.py     match score, UK red flags, ATS alignment
  generate.py    LLM: CV routing, bullet edits, cover letter
  verify.py      anti-fabrication checks
  cv/
    loader.py    read .docx variants, extract text + structure
    editor.py    format-preserving .docx edits (run-level, keeps styling)
    router.py    pick best variant for a job
  sources/
    base.py      Job dataclass + adapter interface
    reed.py      Reed Jobseeker API
    adzuna.py    Adzuna UK
    greenhouse.py / lever.py   ATS boards, no auth
    linkedin_apify.py          Apify actor valig/linkedin-jobs-scraper
scripts/
  init_db.py           create tables, load CV variants
  import_seen_jobs.py  migrate legacy seen_jobs.json
  run_ingest.py        daily pull, score, generate
```

## Format preservation

`cv/editor.py` edits `.docx` at the **run** level, never by rebuilding the document.
A paragraph's runs carry the font, size, bold, spacing. Replacing `run.text` keeps all of
it. Deleting a paragraph and writing a new one loses it. Always take the first path.

When a bullet must be rewritten, keep the length within ±15% of the original so line
wrapping and page breaks do not shift.

## Commands

```bash
python scripts/init_db.py          # first run
python scripts/import_seen_jobs.py # migrate the 99 legacy IDs
python scripts/run_ingest.py       # daily pull
uvicorn app.main:app --reload      # review queue at localhost:8000
```

## Conventions

- Job IDs are `source:external_id`, e.g. `reed:57030691`. Keep this format; the legacy
  `seen_jobs.json` uses it.
- Money and cost tracking go in `daily_stats`. Every LLM and Apify call increments it.
- Scoring runs **before** any LLM call. Never pay to tailor a job that scores below threshold.
- The India CV variant is excluded from routing. Never select it.
