# Deploy TESTIFAI everywhere

TESTIFAI is one FastAPI service that serves both the API and the phone/web app.
Deploy that one service and you get the whole thing: `/app` is the installable
iPhone/Android/desktop app, `/advocacy/*` is the API.

**The only thing every deploy needs:** an `ANTHROPIC_API_KEY` environment
variable. `OPENSTATES_API_KEY` is optional (adds state legislators).

> All commands below assume this `testifai/` folder. On platforms that build the
> whole repo, set the **Root Directory / source** to `testifai`.

---

## Fastest paths (pick any)

### Fly.io (global, free tier)
```bash
cd testifai
fly launch --now                       # detects the Dockerfile
fly secrets set ANTHROPIC_API_KEY=sk-ant-...   # + optional OPENSTATES_API_KEY
```
Your app: `https://<app-name>.fly.dev/app`

### Render
- One click: **New → Blueprint**, point at this repo. `render.yaml` sets root
  dir `testifai`, health check `/health`, and prompts for the two env vars.
- Or manually: **New → Web Service** → Root Directory `testifai`,
  Build `pip install -r requirements.txt`,
  Start `uvicorn main:app --host 0.0.0.0 --port $PORT`, add `ANTHROPIC_API_KEY`.

### Railway
```bash
cd testifai
railway init && railway up
railway variables set ANTHROPIC_API_KEY=sk-ant-...
```
`railway.json` already sets the start command and `/health` check. In the
dashboard set Root Directory to `testifai` if deploying the whole repo.

### Google Cloud Run (scales to zero, pay per use)
```bash
cd testifai
gcloud run deploy testifai --source . --allow-unauthenticated \
  --set-env-vars ANTHROPIC_API_KEY=sk-ant-...
```

### Any Docker host (DigitalOcean, Koyeb, Azure, AWS, a VPS…)
```bash
cd testifai
docker build -t testifai .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... testifai
```
Open http://localhost:8000/app

### Heroku
```bash
cd testifai
heroku create
heroku config:set ANTHROPIC_API_KEY=sk-ant-...
git subtree push --prefix testifai heroku main    # from repo root
```
`app.json` + `Procfile` are included.

---

## Put the app on your iPhone
Open the deployed `/app` URL in **Safari → Share → Add to Home Screen**. It
installs as a standalone app: script generation, in-app teleprompter with
color controls, on-device read-aloud, and share-sheet save.

## Custom domain
Point a domain at whichever host you chose (each has a "custom domain" setting).
`https://testifai.app/app` etc. HTTPS is automatic on all of the above.

## Hosting the app UI on a static CDN (optional)
The API must run on one of the hosts above (it needs Python + your key). If you
also want the UI on a CDN (Cloudflare Pages, Netlify, Vercel, GitHub Pages),
serve a page that sets the API base first:
```html
<script>window.TESTIFAI_API_BASE = "https://your-api-host";</script>
```
CORS is already open on the backend, so the CDN-hosted UI can call it.

## Health & diagnostics
- `GET /health` — liveness (used by the platform health checks).
- `GET /diagnostic` — checks the Claude key + the live congress data source.
