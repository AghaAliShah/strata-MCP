# Deploying Strata

## Read this first: why Vercel alone is not enough

Strata is **two processes**, and that shapes the deployment:

1. `backend/` (FastAPI) spawns `mcp_server/` as a **long-lived subprocess** at startup and
   keeps one MCP session open for the life of the app.
2. Analysis requests **stream** (SSE) and take **30–90 seconds**.

Vercel functions are **ephemeral** — they start per request, can't hold a persistent
subprocess between requests, and are duration-capped. Deploying the backend there would
mean re-spawning the MCP server on every request and racing the timeout.

So the standard split is:

| Piece | Host | Why |
|---|---|---|
| `frontend/` | **Vercel** | Static file, instant, free, global CDN |
| `backend/` + `mcp_server/` | **Render / Railway / Fly.io** | Persistent process, no duration cap, SSE works |

---

## Step 1 — Deploy the backend (Render, free tier)

1. Push this repo to GitHub.
2. On [render.com](https://render.com) → **New → Web Service** → connect the repo.
3. Settings:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables (same keys as your `.env`):
   - `GITHUB_TOKEN`
   - `OPENROUTER_API_KEY`
   - `OPENROUTER_MODEL`
5. Deploy, then copy the public URL, e.g. `https://strata-api.onrender.com`.

> Render's free tier sleeps after inactivity — the first request after idle takes ~30s to
> wake. Fine for a portfolio demo.

CORS is already open in `backend/main.py`, so the Vercel frontend can call it. To lock it
down to your own domain, replace `allow_origins=["*"]` with your Vercel URL.

## Step 2 — Point the frontend at that backend

Edit `frontend/config.js`:

```js
window.STRATA_API_BASE = "https://strata-api.onrender.com";
```

No trailing slash. Commit it.

## Step 3 — Deploy the frontend to Vercel

```bash
npm i -g vercel
vercel
```

Accept the defaults. `vercel.json` already sets `outputDirectory` to `frontend`, so Vercel
serves it as a static site with no build step.

Or via the dashboard: **Add New → Project** → import the repo → Framework Preset **Other**
→ Output Directory `frontend` → Deploy.

For production:

```bash
vercel --prod
```

---

## Running everything locally (unchanged)

`config.js` ships with `STRATA_API_BASE = ""`, which means same-origin — so locally FastAPI
serves both the UI and the API and nothing else is needed:

```bash
.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8055
```

http://127.0.0.1:8055

---

## If you really want everything on Vercel

Possible, but not recommended: you would need to drop the persistent MCP session and spawn
the MCP server per request inside the function, then keep every analysis under Vercel's
max duration. You lose the streaming activity panel on slower repos and pay a subprocess
cold start each time. The two-host split above is both simpler and closer to how MCP
servers are meant to be hosted.
