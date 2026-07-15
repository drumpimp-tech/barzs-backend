# TESTIFAI

A standalone backend + phone/web app. You pick a real legislator, pick a use of
AI, set a goal and a length, and TESTIFAI writes you a short spoken script,
scrubs it against the **Blackout list** (no em dashes, no AI-sounding words),
and lets you read it on a built-in teleprompter.

This is its own service. It does not depend on any other project.

## Run locally

```bash
cd testifai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY (+ optional OPENSTATES_API_KEY)
uvicorn main:app --reload
```

- App (phone + web):  http://localhost:8000/app
- API docs:           http://localhost:8000/docs
- Health:             http://localhost:8000/health
- Key check:          http://localhost:8000/diagnostic

## On an iPhone

Open the deployed `/app` URL in Safari, then **Share → Add to Home Screen**.
It installs as a standalone app (PWA) with full functionality: script
generation, an in-app teleprompter with background/text colors, and on-device
read-aloud that highlights and auto-scrolls. Saving a script uses the iOS
share sheet.

## API

| Method | Path | Purpose |
|---|---|---|
| GET  | `/advocacy/states` | 50 states + DC |
| GET  | `/advocacy/applications` | 100+ AI topics |
| GET  | `/advocacy/goals` | advocacy goals |
| GET  | `/advocacy/blacklist` | the Blackout list of banned AI terms |
| GET  | `/advocacy/legislators?state=CA&chamber=all` | live legislators for a state |
| POST | `/advocacy/generate` | write a script (returns text + teleprompter URL) |
| POST | `/advocacy/download` | script as a downloadable `.txt` |
| GET  | `/advocacy/teleprompter` | standalone teleprompter page |
| GET  | `/app` | the TESTIFAI web/PWA app |

## Data sources

- **U.S. Senators + Representatives** — the key-free unitedstates.io dataset,
  fetched live and cached.
- **State legislators** — Open States API when `OPENSTATES_API_KEY` is set.
- **Script writing** — Anthropic Claude.

## Deploy

See **[DEPLOY.md](DEPLOY.md)** for one-command/one-click deploys to Fly.io,
Render, Railway, Google Cloud Run, Heroku, and any Docker host. Every path needs
only `ANTHROPIC_API_KEY` (and optionally `OPENSTATES_API_KEY`). A `Dockerfile`,
`render.yaml`, `fly.toml`, `railway.json`, `app.json`, and `Procfile` are all
included so the service runs anywhere.
