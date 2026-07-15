"""
TESTIFAI backend.

A standalone service (its own app, not part of any other project) that powers
the TESTIFAI phone/web app: write AI testimony addressed to real legislators,
scrub it against the Blackout list, and read it on a built-in teleprompter.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv

load_dotenv(override=True)

from routes import api, webapp

app = FastAPI(title="TESTIFAI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router,    prefix="/advocacy", tags=["TESTIFAI"])
app.include_router(webapp.router, prefix="/app",      tags=["App"])


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app")


@app.get("/health")
async def health():
    return {"status": "TESTIFAI backend is live"}


@app.get("/diagnostic")
async def diagnostic():
    """Reports whether the keys TESTIFAI needs are working. Use to debug 401/502s."""
    import os
    import httpx

    results = {}

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        results["anthropic"] = {"status": "MISSING", "detail": "ANTHROPIC_API_KEY not set"}
    else:
        try:
            import anthropic as _anthropic
            c = _anthropic.AsyncAnthropic(api_key=anthropic_key)
            await c.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            results["anthropic"] = {"status": "OK"}
        except Exception as e:
            results["anthropic"] = {"status": "ERROR", "detail": str(e)[:200]}

    # Congress data source (no key needed).
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("https://theunitedstates.io/congress-legislators/legislators-current.json")
        results["congress_data"] = {"status": "OK" if r.status_code == 200 else "ERROR", "http_status": r.status_code}
    except Exception as e:
        results["congress_data"] = {"status": "ERROR", "detail": str(e)[:200]}

    # Open States (optional) enables state legislators.
    os_key = os.environ.get("OPENSTATES_API_KEY", "")
    results["openstates"] = {"status": "CONFIGURED" if os_key else "NOT_CONFIGURED",
                             "detail": "Optional. Adds state legislature members when set."}

    all_ok = all(v["status"] in ("OK", "CONFIGURED", "NOT_CONFIGURED") for v in results.values())
    return {"overall": "OK" if all_ok else "DEGRADED", "keys": results}


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Privacy Policy - TESTIFAI</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background:#0d0d0d; color:#e0e0e0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
    font-size:16px; line-height:1.7; padding:40px 20px 80px; max-width:740px; margin:0 auto; }
  h1 { color:#c9a84c; font-size:2rem; margin-bottom:4px; }
  h2 { color:#c9a84c; font-size:1.1rem; margin:32px 0 10px; text-transform:uppercase; letter-spacing:.04em; }
  p { margin-bottom:14px; color:#ccc; } ul { margin:0 0 14px 20px; color:#ccc; } li { margin-bottom:6px; }
  a { color:#c9a84c; } .meta { color:#888; font-size:.85rem; margin-bottom:24px; }
  hr { border:none; border-top:1px solid #222; margin:28px 0; }
</style></head><body>
<h1>Privacy Policy - TESTIFAI</h1>
<p class="meta">Last updated: 2026</p>
<hr>
<h2>What TESTIFAI does</h2>
<p>TESTIFAI helps you write a short spoken script addressed to an elected official about a use of AI, and read it on a built-in teleprompter. It is a writing and delivery tool.</p>
<h2>Information you provide</h2>
<p>To personalize a script you may enter your name, gender, age, home state, and links to your public social channels. You also choose a legislator, an AI topic, a goal, and a length. This information is sent to the TESTIFAI backend only to generate your script and is not stored after the response is returned. No account is created.</p>
<h2>How your script is generated</h2>
<p>Your selections are sent to Anthropic's Claude API to write the script. If you provide social links, the backend fetches the public web page for each to add context. Public legislator data comes from the unitedstates.io dataset and, if configured, the Open States API.</p>
<h2>On-device features</h2>
<p>The teleprompter's read-aloud uses your device's built-in speech voices. Nothing you read is recorded or uploaded by TESTIFAI.</p>
<h2>Data we keep</h2>
<p>The backend does not maintain a user database and does not retain request content after a script is returned.</p>
<h2>Contact</h2>
<p>Questions: <a href="mailto:drumpimp@gmail.com">drumpimp@gmail.com</a></p>
</body></html>"""
