# Deploy to Railway in 10 minutes

**Cost: £0/month**

## 1. Create a GitHub account (if you don't have one)

Go here: https://github.com/signup

Fill in username, email, password. Verify your email. Done.

## 2. Upload your job-hunter code to GitHub

Open your terminal/command prompt and paste this (one line at a time):

```bash
cd "C:\Users\Sachin\OneDrive\Desktop\G-Drive\Job Apps\CV\job-hunter"
git init
git config user.name "Your Name"
git config user.email "your.email@example.com"
git add .
git commit -m "Initial commit"
git branch -M main
```

Now create a repo on GitHub:
- Go to https://github.com/new
- Name: `job-hunter`
- Description: "Job application automation"
- Click **Create repository**

Back in your terminal, paste:

```bash
git remote add origin https://github.com/YOUR_USERNAME/job-hunter.git
git push -u origin main
```

(Replace `YOUR_USERNAME` with your actual GitHub username. When asked for a password, go here: https://github.com/settings/tokens/new → check `repo` → click **Generate token** → copy it → paste as your password.)

## 3. Sign up for Railway

Go here: https://railway.app

Click **Create Account** → **Continue with GitHub** → authorize.

## 4. Deploy

In Railway dashboard, click **+ New Project** → **Deploy from GitHub repo**.

Click **Configure GitHub App** and authorize Railway to see your repos.

Select `job-hunter` from the list.

Railway will auto-detect it's Python and start building. Wait 2-3 minutes. When it says "Deployed ✓", you're live.

Copy your app URL (looks like `https://job-hunter-abc123.railway.app`). Open it in a browser. You should see the app.

## 5. Add your keys

In Railway dashboard, click your **job-hunter** service.

Click the **Variables** tab.

Add these (get free keys from the links below):

| Key | Value | Get it from |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | https://console.anthropic.com/account/keys |
| `REED_API_KEY` | Your key | https://www.reed.co.uk/developers/Jobseeker |
| `ADZUNA_APP_ID` | Your ID | https://developer.adzuna.com/ |
| `ADZUNA_APP_KEY` | Your key | https://developer.adzuna.com/ |
| `APIFY_TOKEN` | Your token (optional) | https://console.apify.com/account/integrations |

(The APIFY line is optional. If you don't add it, LinkedIn jobs just won't pull. Everything else works fine.)

Click **Deploy** to redeploy with the new keys.

## 6. Add your CVs

Your CVs need to be in the repo so Railway can see them.

**Download your cloud-only CV files first:**

- Go to `C:\Users\Sachin\OneDrive\Desktop\G-Drive\Job Apps\CV\FEA CV\`
- Right-click the folder → **Always keep on this device**
- Wait for it to download (look for a green checkmark icon)
- Do the same for `Process Quality based CV` folder

**Now add them to the repo:**

```bash
cd "C:\Users\Sachin\OneDrive\Desktop\G-Drive\Job Apps\CV\job-hunter"

mkdir -p data/cv_variants

copy "..\Sachin_CV.docx" "data/cv_variants/General.docx"
copy "..\NPI&R&D\Sachin_CV_Dyson_NPI_Graduate.docx" "data/cv_variants/NPI_and_RandD.docx"
copy "..\Commercial Client Facing\Sachin_CV_Littlefuse.docx" "data/cv_variants/Commercial.docx"
copy "..\FEA CV\Sachin_CV.docx" "data/cv_variants/FEA.docx"
copy "..\Process Quality based CV\Sachin_CV.docx" "data/cv_variants/Process_Quality.docx"

git add data/
git commit -m "Add CV variants"
git push
```

Wait 2-3 minutes for Railway to redeploy.

## 7. Add your skills profile

```bash
copy "..\Commercial Client Facing\MASTER_SKILLS_PROFILE.md" "data/MASTER_SKILLS_PROFILE.md"

git add data/
git commit -m "Add master skills profile"
git push
```

Wait for Railway to redeploy again.

## 8. Test it

Open your Railway app URL in a browser (e.g., `https://job-hunter-abc123.railway.app`).

Click the **Run ingest** button.

Wait 30 seconds. You should see pulled/qualified counts.

## 9. Set up daily pulls (pick one)

### Option A: GitHub Actions (easiest)

Create a file `.github/workflows/daily.yml` in your repo:

```bash
mkdir -p .github/workflows
```

Create the file with this content (copy-paste into a text editor, save as `.github/workflows/daily.yml`):

```yaml
name: Daily job pull

on:
  schedule:
    - cron: '0 6 * * *'

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

Replace `YOUR_APP_URL` with your actual Railway URL (e.g., `https://job-hunter-abc123.railway.app`).

Then:

```bash
git add .github/
git commit -m "Add daily ingest"
git push
```

**Done.** Every day at 6 AM UTC, it pulls new jobs automatically.

### Option B: Cron-job.org (no GitHub needed)

Go here: https://cron-job.org/en/

Click **Create cron job**

- **URL:** `https://YOUR_APP_URL.railway.app/api/ingest`
- **Execution time:** `06:00` (6 AM)
- Click **Create**

Done. It runs every day at 6 AM.

## 10. Secure it (IMPORTANT)

**Anyone with your Railway URL can see your CV and all your applications.** You need to protect it.

### Option A: CloudFlare Access (easiest, free)

Go here: https://dash.cloudflare.com/sign-up

Sign up with your email.

Follow the setup wizard (you don't need a domain for this to work).

Go to **Zero Trust** (left sidebar) → **Access** → **Applications**.

Click **Create an application** → **Self-hosted**.

- Name: `job-hunter`
- Subdomain: Leave blank for now
- Domain: We'll skip this for now, just use Railway's URL
- Application type: **Self-hosted**

On the next step:
- **Identity providers:** Click **Add** → **Email** → **Save**

Click **Create application**.

Now you get to add who can access it:
- Click **+ Add a rule**
- Name: `Allow myself`
- Condition: **Emails** → type your email
- Action: **Allow**
- Click **Save rule**

Now, whenever you visit your Railway URL, you'll be asked to log in with your email. Only you can access it.

### Option B: Simple password (if you don't want to use Cloudflare)

Edit your code locally. Open `app/main.py`, add this at the very top:

```python
import os
from fastapi import Request, HTTPException
```

Add this decorator right before `@app.get("/", response_class=HTMLResponse)`:

```python
@app.middleware("http")
async def check_auth(request: Request, call_next):
    if request.url.path.startswith("/static/"):
        return await call_next(request)
    if request.url.path == "/api/health":
        return await call_next(request)
    
    auth = request.headers.get("authorization", "")
    token = os.getenv("APP_TOKEN", "changeme")
    if auth != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await call_next(request)
```

In Railway Variables, add:

```
APP_TOKEN=your-secret-password-here
```

Now, to use the app from your browser, you'll need to install a browser extension that adds the auth header (like Requestly or Modify Header Value), which is annoying.

**Recommendation: Use CloudFlare Access (Option A).** It's simpler and built for this.

## Done!

Your app is now live at your Railway URL.

**To use it:**

1. Open the URL in a browser
2. Log in (if you set up CloudFlare Access)
3. Click **Run ingest** to pull jobs today
4. Review the queue
5. Use `A` to apply, `S` to skip

**Daily, at 6 AM UTC, new jobs pull automatically.**

---

## Costs

- **Railway:** £0/month (free tier)
- **CloudFlare:** £0/month (free tier)
- **Anthropic LLM:** ~£7–20/month (you control this, it's optional)
- **Apify LinkedIn:** ~£0.50/month (optional, turn off if you don't want)

**Total: £0–20/month depending on what you use.**

---

## Stuck?

**Railway won't deploy?**
- Check logs: click your service → **Logs**
- Look for error messages and Google them

**CVs not loading?**
- Did you download the cloud-only files? Right-click folder → **Always keep on this device**
- Did you commit them? Check that `data/cv_variants/` has files in your GitHub repo

**No jobs pulling?**
- Check that your API keys are correct
- Missing REED_API_KEY or ADZUNA keys? Some sources just skip, that's fine
- Click **Run ingest** and wait 30 seconds

**Need help?**
- Post in the Railway Discord: https://discord.gg/railway
- Or email Anthropic support if it's an LLM issue
