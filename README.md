# Job Hunter

Daily UK job pipeline for a graduate mechanical engineer. Pulls listings, scores them
offline, routes each to the best of your existing CV variants, lifts ATS alignment using
only skills you can actually evidence, drafts a cover letter, and hands you a review
queue. You click submit. Nothing auto-applies.

## How the alignment lift works

This is the part worth understanding, because it is what stops the tool becoming a
liability.

Your `MASTER_SKILLS_PROFILE.md` lists far more than any single CV does. Each CV variant
is a deliberate subset. So when a job asks for something a given CV omits, there are two
possibilities:

1. **The master profile claims it.** You have it, this CV just does not mention it. The
   tool works it into an existing bullet or appends it to a skills line. Alignment rises,
   nothing is invented.
2. **The master profile does not claim it.** The tool drops it, lists it under
   "honest gaps", and your score stays where it is.

The self-test demonstrates case 2 directly: given a job wanting SolidWorks, ANSYS, GD&T,
DFMEA, Minitab, Six Sigma and CATIA, it accepts Minitab and Six Sigma and refuses CATIA,
because CATIA appears nowhere in your profile. If a job needs skills you do not have,
you will see 70-something, not 90. That number is the useful one.

Three layers enforce this:

- `verify.verify_skill_additions` gates every keyword before it reaches the model
- the system prompt in `generate.py` forbids invention outright
- `verify.check` re-scans the model's output for unsourced credentials, years, metrics
  and organisation names, and flags the card for manual review if it finds any

## Format preservation

Edits happen at the **run** level inside the `.docx`. A run carries the font, size, weight
and spacing, so rewriting `run.text` leaves the document visually identical apart from the
words. The tool never deletes and re-adds a paragraph, which is what loses formatting.

Two guards back this up: a rewrite must stay within 15% of the original character length
so line wrapping and page breaks do not shift, and the original text must still match
before an edit lands, so a stale paragraph index cannot corrupt the wrong bullet. The
self-test asserts style, font name, size, bold and paragraph count are all unchanged
after an edit.

## Setup

```bash
cd job-hunter
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # then fill in your keys
python scripts/selftest.py  # 33 checks, no network or keys needed
python scripts/init_db.py
python scripts/import_seen_jobs.py
python scripts/run_ingest.py
uvicorn app.main:app --reload
```

Open http://localhost:8000.

### Keys

| Key | Needed for | Cost |
|---|---|---|
| `ANTHROPIC_API_KEY` | tailoring, cover letters | ~$10-30/mo |
| `REED_API_KEY` | Reed, your biggest source | free, [reed.co.uk/developers](https://www.reed.co.uk/developers) |
| `ADZUNA_APP_ID` / `_KEY` | Adzuna UK | free ~1,000 calls/mo, [developer.adzuna.com](https://developer.adzuna.com/) |
| `APIFY_TOKEN` | LinkedIn | ~$0.60/mo |

Everything runs without `APIFY_TOKEN`. Sources with missing keys are skipped, not fatal.
The ATS adapters (Greenhouse, Lever, Ashby, Workable) need no key at all.

### OneDrive note

The CV folder is cloud-synced. Two variants (FEA, Process Quality) were cloud-only
placeholders at build time and got skipped with a warning. To include them, right-click
the CV folder in Explorer and choose **Always keep on this device**, then re-run
`init_db.py`. The Design Engineer folder holds only a PDF, so add the `.docx` there if
you want that variant routable.

## Daily use

```
J / K   move through the queue
A       copy cover letter, open the posting, mark sent
S       skip with a reason
```

Cards are sorted by match score. Each shows the routed CV variant and why, the alignment
before and after, the exact bullet rewrites as a diff, the honest gaps, and any red flags.
Anything the fabrication guard tripped on is marked **Needs review** and should be read
before sending.

## Scoring

100 points: skills 35, experience fit 25, commute 15, sector 15, salary 10.

UK red flags, which is where most of the value sits:

- **Security clearance** (SC, DV, BPSS) zeroes the score unless `HAS_CLEARANCE=true`.
  Rules out a lot of BAE, MBDA, Leonardo and Rolls-Royce defence work
- **No sponsorship** zeroes it if `NEEDS_SPONSORSHIP=true`
- **"Junior" titles wanting 2+ years**, parsed from body text, not the title. Your
  25 July report caught this twice in twenty listings
- **Chartership required** takes 25 points off
- **Agency reposts** are flagged and fuzzy-deduped against the same role elsewhere

Scoring runs before any API call, so you never pay to tailor a job that was never viable.

## Publishing

The app is a standard ASGI service, so anything that runs a container works.

**Fly.io** (has a free allowance, good for a personal tool):

```bash
fly launch --no-deploy
fly secrets set ANTHROPIC_API_KEY=... REED_API_KEY=... ADZUNA_APP_ID=... ADZUNA_APP_KEY=...
fly deploy
```

**Railway or Render:** point at the repo, set the start command to
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, add the same env vars.

**Docker:** a `Dockerfile` is included, `docker build -t job-hunter . && docker run -p 8000:8000 --env-file .env job-hunter`.

Two things to sort before it is public:

1. **Add auth.** There is none. It is built as a single-user local tool. If you host it
   on the open internet, put Cloudflare Access in front or add HTTP basic auth, otherwise
   anyone with the URL sees your CV and application history.
2. **Move off SQLite** if the host has an ephemeral filesystem. Set `DATABASE_URL` to a
   Postgres connection string; SQLModel handles the rest with no code change.

For the daily pull, point any scheduler at `POST /api/ingest`, or run
`python scripts/run_ingest.py` from cron:

```
0 6 * * *  cd /path/to/job-hunter && .venv/bin/python scripts/run_ingest.py
```

## On the 50-a-day target

50 is a sourcing number, not a send number. The realistic pool of genuinely suitable new
graduate mechanical postings in the UK per day is smaller than 50, and applying to badly
matched roles mostly generates rejections while spending goodwill at companies worth a
considered application later. Your existing pipeline found 99 quality-filtered jobs over
about two weeks, which is the honest baseline. Expect 50 to 80 pulled, 20 to 30 above
threshold, 15 to 25 worth sending on a good day.

The dashboard reports reply rate by CV variant, which after a few weeks answers the
question actually worth knowing: which of your CVs gets responses.

## Layout

```
app/
  main.py       FastAPI + review queue API
  pipeline.py   daily orchestration
  scoring.py    match score, UK red flags, ATS alignment
  generate.py   LLM tailoring
  verify.py     anti-fabrication guards
  cv/           loader, format-preserving editor, variant router
  sources/      reed, adzuna, ats (greenhouse/lever/ashby/workable), linkedin_apify
scripts/
  selftest.py           33 offline checks
  init_db.py            tables + CV variants + seed sources
  import_seen_jobs.py   migrate the 99 legacy IDs
  run_ingest.py         daily pull
```

## Limits

- No auto-submit, by design. No applicant-side submission API exists; Greenhouse and
  Lever both authenticate with the *employer's* secret key
- LinkedIn via Apify keeps your own account out of it, but remains contrary to LinkedIn's
  User Agreement. Personal-scale use, no republishing. The adapter is behind a config
  switch if the actor goes dark
- Commute distances come from a lookup table in `sources/base.py`, not a geocoding API.
  Add towns as you need them
- Reply tracking is manual for now
