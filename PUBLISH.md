# Publish Job Hunter for Free

**Platform: Railway** (free tier, easiest path)

Railway gives you free compute, a free Postgres database, and automatic deploys from GitHub. Total cost: £0. No credit card needed for the free tier.

## Step 1: Push to GitHub

```bash
cd ~/Desktop/G-Drive/Job\ Apps/CV/job-hunter
git init
git add .
git commit -m "Initial commit: job hunter app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/job-hunter.git
git push -u origin main
```

(Replace `YOUR_USERNAME` with your actual GitHub username. If you haven't pushed to GitHub before, generate a personal access token at https://github.com/settings/tokens and use it as your password.)

## Step 2: Set up Railway

1. Go to https://railway.app
2. Click **Create Account**, sign up with GitHub
3. Click **New Project** → **Deploy from GitHub repo**
4. Authorize Railway to access your GitHub
5. Select the `job-hunter` repo
6. Railway auto-detects it's a Python app and sets `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## Step 3: Add environment variables

In the Railway dashboard for your project:

1. Click **Variables**
2. Add these (get keys from `.env.example` instructions):

```
ANTHROPIC_API_KEY=sk-ant-...
REED_API_KEY=...
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
APIFY_TOKEN=...
DATABASE_URL=  # Leave blank, Railway sets this automatically
```

3. Click **Deploy**

## Step 4: Initialize the database

Once the app is running on Railway:

1. Copy the app's public URL from the Railway dashboard (looks like `https://job-hunter-abc123.railway.app`)
2. Open your terminal and run:

```bash
curl -X POST https://job-hunter-abc123.railway.app/api/ingest
```

This creates the database tables.

## Step 5: Upload your CVs

The app needs your CV files. Two ways:

### Option A: Mount them (recommended for this setup)

Railway doesn't have a persistent filesystem by default, so CVs won't survive a redeploy. Instead, add them to git (but not secrets):

```bash
# Copy your CVs into the repo
mkdir -p data/cv_variants
cp ~/Desktop/G-Drive/Job\ Apps/CV/Sachin_CV.docx data/cv_variants/General.docx
cp ~/Desktop/G-Drive/Job\ Apps/CV/NPI\&R\&D/Sachin_CV_Dyson_NPI_Graduate.docx data/cv_variants/NPI_and_RandD.docx
cp ~/Desktop/G-Drive/Job\ Apps/CV/Commercial\ Client\ Facing/Sachin_CV_Littlefuse.docx data/cv_variants/Commercial.docx

git add data/
git commit -m "Add CV variants"
git push
```

Wait for Railway to auto-redeploy (watch the dashboard).

### Option B: Use Postgres to store PDFs (advanced)

Skip this for now. Just commit the .docx files to git.

## Step 6: Copy your master profile

```bash
cp ~/Desktop/G-Drive/Job\ Apps/CV/Commercial\ Client\ Facing/MASTER_SKILLS_PROFILE.md data/MASTER_SKILLS_PROFILE.md
git add data/
git commit -m "Add master skills profile"
git push
```

## Step 7: Import legacy jobs

Once deployed, visit the app and click **Run ingest** to pull today's jobs. This also hydrates the database with the CV variants.

Then, run this locally to import your 99 existing IDs:

```bash
python scripts/import_seen_jobs.py
```

(This reads from your local `seen_jobs.json`. If you want to import them into the live database, you'll need to wire up SSH access to the Railway Postgres, which is out of scope. For now, the live instance starts fresh.)

## Step 8: Set up daily pulls

Railway doesn't have a built-in scheduler, so use a free external service. Pick one:

### Option A: GitHub Actions (free, easiest)

Create `.github/workflows/daily.yml`:

```yaml
name: Daily job pull

on:
  schedule:
    - cron: '0 6 * * *'  # 6 AM UTC every day

jobs:
  ingest:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger ingest
        run: |
          curl -X POST https://YOUR_APP_URL.railway.app/api/ingest \
            -H "Content-Type: application/json" \
            -d '{}'
```

Replace `YOUR_APP_URL` with your Railway URL. Commit and push:

```bash
git add .github/workflows/daily.yml
git commit -m "Add daily ingest workflow"
git push
```

### Option B: Cron-job.org (free, no GitHub needed)

1. Go to https://cron-job.org/en/
2. Click **Create cron job**
3. URL: `https://YOUR_APP_URL.railway.app/api/ingest`
4. Execution time: **06:00 every day**
5. Save

## Step 9: Secure it

**Critical: Your app is public with no authentication.** Anyone with the URL can see your CV and application history.

Add HTTP Basic Auth to Railway:

1. In the Railway dashboard, go to **Settings** for your service
2. Scroll to **Port** and click **Edit**
3. Find the **Port** value and add Auth:
   - Under **Region**, click **Add Environment Variable**
   - `HTTP_AUTH_USER=job`
   - `HTTP_AUTH_PASS=` (generate a strong password)

Actually, Railway doesn't support this directly. Instead, use a simpler approach:

**Use CloudFlare Access (free tier):**

1. Go to https://dash.cloudflare.com
2. Sign up (free)
3. Add a domain or use a free Cloudflare domain
4. Go to **Zero Trust** (left sidebar)
5. Click **Access** → **Tunnels**
6. Create a new tunnel, connect your Railway app
7. Set an access policy: **Emails you want to allow**

This sits in front of your app and requires you to log in with your email before you see anything.

**Or: Add a simple password in the app itself**

Edit `app/main.py`, add at the top:

```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi import HTTPException

@app.middleware("http")
async def auth_middleware(request, call_next):
    if request.url.path == "/health":
        return await call_next(request)  # always allow health checks
    auth = request.headers.get("authorization", "")
    expected = "Bearer " + os.getenv("APP_TOKEN", "change-me-in-env-vars")
    if auth != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await call_next(request)
```

Add to `.env`:

```
APP_TOKEN=your-secret-token-here
```

Then every request needs:

```bash
curl -H "Authorization: Bearer your-secret-token-here" https://your-app.railway.app/api/queue
```

## Step 10: Test

1. Open your Railway app URL in a browser
2. You should see the review queue (empty on first run)
3. Click **Run ingest** to pull today's jobs
4. The dashboard should show pulled/qualified/tailored counts

## Troubleshooting

**"Connection refused" on `/api/ingest`**

The app takes ~30 seconds to boot. Wait and try again. Check the Railway logs: click your service → **Logs**.

**CVs not loading**

Either they're not in `data/cv_variants/` or they're still cloud-only OneDrive files. Run locally first:

```bash
python scripts/init_db.py
```

This will skip cloud-only files and tell you which ones. Download those files in Explorer (open them once to hydrate), commit them to git, and redeploy.

**Database errors on first run**

Railway auto-creates `DATABASE_URL` and the tables are created on startup. If it still fails, click into the Railway service → **Data** and check the Postgres status.

**Ingest runs but pulls nothing**

Check that your API keys are set (REED_API_KEY, ADZUNA_APP_ID, etc). Missing keys just skip that source, which is fine, but you need at least one. See the logs: click the service → **Logs** → filter for the adapter names (reed, adzuna, etc).

## Ongoing costs

**£0/month guaranteed.**

Railway's free tier includes:
- 500 hours of compute per month (enough for a daily 5-minute run)
- 5GB of Postgres storage
- Unlimited bandwidth

The only thing that costs money:
- LLM API calls (Anthropic ~$10-30/mo), controlled by you
- Apify LinkedIn (~$0.60/mo), you turn this off in `.env` if it's too much

That's it. No hidden fees, no credit card needed to start.

## Next: integrate with your local setup

Once it's running on Railway, you can:

1. **Keep local .env separate** – your laptop has dev keys, Railway has prod keys
2. **Push changes from Claude Code** – make edits locally, commit, Railway auto-redeploys
3. **Mirror responses locally** – if you want to download generated CVs and cover letters for archival, add a sync script that pulls from Railway's Postgres

For now, the app is live. Visit the URL, run ingest, and review jobs in the queue.
