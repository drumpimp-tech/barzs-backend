from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv
import os

load_dotenv(override=True)

from routes import analysis, lyrics, transcribe, dictionary, tts, advocacy, webapp

app = FastAPI(title="BARZS Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router,   prefix="/analyze",    tags=["Analysis"])
app.include_router(lyrics.router,     prefix="/lyrics",     tags=["Lyrics"])
app.include_router(transcribe.router, prefix="/transcribe", tags=["Transcription"])
app.include_router(dictionary.router, prefix="/dictionary", tags=["Dictionary"])
app.include_router(tts.router,        prefix="/tts",        tags=["TTS"])
app.include_router(advocacy.router,   prefix="/advocacy",   tags=["TESTIFAI"])
app.include_router(webapp.router,     prefix="/app",        tags=["TESTIFAI App"])


@app.get("/health")
async def health():
    return {"status": "BARZS backend is live"}


@app.get("/testifai", include_in_schema=False)
async def testifai_shortcut():
    return RedirectResponse(url="/app")


@app.get("/diagnostic")
async def diagnostic():
    """Tests every API key and reports which ones are working. Use to debug 401 errors."""
    import httpx

    results = {}

    # Test Genius
    genius_token = os.environ.get("GENIUS_ACCESS_TOKEN", "")
    if not genius_token:
        results["genius"] = {"status": "MISSING", "detail": "GENIUS_ACCESS_TOKEN not set in Railway environment variables"}
    else:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    "https://api.genius.com/search",
                    headers={"Authorization": f"Bearer {genius_token}"},
                    params={"q": "test"},
                )
            if r.status_code == 200:
                results["genius"] = {"status": "OK"}
            else:
                results["genius"] = {"status": "ERROR", "http_status": r.status_code, "detail": r.text[:200]}
        except Exception as e:
            results["genius"] = {"status": "ERROR", "detail": str(e)}

    # Test Anthropic
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        results["anthropic"] = {"status": "MISSING", "detail": "ANTHROPIC_API_KEY not set in Railway environment variables"}
    else:
        try:
            import anthropic as _anthropic
            c = _anthropic.AsyncAnthropic(api_key=anthropic_key)
            msg = await c.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            results["anthropic"] = {"status": "OK"}
        except Exception as e:
            results["anthropic"] = {"status": "ERROR", "detail": str(e)[:200]}

    # ElevenLabs (optional)
    el_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not el_key:
        results["elevenlabs"] = {"status": "NOT_CONFIGURED", "detail": "Optional — app uses iOS voices if missing"}
    else:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": el_key})
            results["elevenlabs"] = {"status": "OK" if r.status_code == 200 else "ERROR", "http_status": r.status_code}
        except Exception as e:
            results["elevenlabs"] = {"status": "ERROR", "detail": str(e)}

    all_ok = all(v["status"] in ("OK", "NOT_CONFIGURED") for v in results.values())
    return {"overall": "OK" if all_ok else "DEGRADED", "keys": results}


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Privacy Policy — BAŘ$</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0d0d0d;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 16px;
    line-height: 1.7;
    padding: 40px 20px 80px;
    max-width: 740px;
    margin: 0 auto;
  }
  h1 { color: #c9a84c; font-size: 2rem; margin-bottom: 4px; }
  .meta { color: #888; font-size: 0.85rem; margin-bottom: 32px; }
  h2 { color: #c9a84c; font-size: 1.1rem; margin: 36px 0 10px; letter-spacing: 0.04em; text-transform: uppercase; }
  h3 { color: #d0b96a; font-size: 1rem; margin: 20px 0 6px; font-weight: 600; }
  p  { margin-bottom: 14px; color: #ccc; }
  ul { margin: 0 0 14px 20px; color: #ccc; }
  li { margin-bottom: 6px; }
  a  { color: #c9a84c; text-decoration: none; }
  a:hover { text-decoration: underline; }
  hr { border: none; border-top: 1px solid #222; margin: 32px 0; }
  .footer { color: #555; font-size: 0.85rem; margin-top: 48px; font-style: italic; }
</style>
</head>
<body>

<h1>Privacy Policy — BAŘ$</h1>
<p class="meta"><strong>Effective Date:</strong> May 17, 2026 &nbsp;|&nbsp; <strong>Last Updated:</strong> May 17, 2026</p>

<hr>

<h2>Overview</h2>
<p>BAŘ$ ("the App") is a rap lyric decoder for iPhone and iPad. This Privacy Policy explains what information is collected when you use BAŘ$, how it is used, and what rights you have over your data. By using BAŘ$, you agree to the practices described here.</p>

<hr>

<h2>1. Information We Collect</h2>

<h3>1.1 Information You Provide</h3>

<h3>Audio Recordings and Uploads</h3>
<p>If you use the Record or Upload features, your audio is processed on your device using Apple's on-device speech recognition framework (SFSpeechRecognizer). Audio is transcribed locally and is not transmitted to BAŘ$ servers. We do not store, retain, or access your audio files.</p>

<h3>Search Queries</h3>
<p>When you search for a song or artist, your query is sent to our backend API hosted at <a href="https://barzs-backend.onrender.com">https://barzs-backend.onrender.com</a> to retrieve results from the Genius music database. Search queries are not linked to your identity and are not stored.</p>

<h3>YouTube Links</h3>
<p>If you paste a YouTube link, the URL is sent to our backend API, which calls the YouTube oEmbed service to retrieve the video title. No video content or audio is downloaded or stored.</p>

<h3>1.2 Information Collected Automatically</h3>

<h3>App Usage</h3>
<p>BAŘ$ does not use analytics SDKs, crash reporting services, or advertising frameworks. No behavioral data, session data, or usage patterns are collected or transmitted by the App itself.</p>

<h3>Device Permissions</h3>
<p>The App may request the following permissions, solely for the features described:</p>
<ul>
  <li><strong>Microphone</strong> — Required to record audio in the Record tab. Audio is processed on-device only.</li>
  <li><strong>Speech Recognition</strong> — Required to transcribe uploaded or recorded audio. Transcription is performed on-device using Apple's SFSpeechRecognizer.</li>
  <li><strong>Photo Library</strong> — Required only if you select album artwork. Images are not uploaded or stored by BAŘ$.</li>
</ul>
<p>Each permission is requested at the point of use, not on launch. You may deny any permission and the rest of the App will continue to function.</p>

<hr>

<h2>2. How We Use Information</h2>
<p>BAŘ$ uses information only to deliver the features you request:</p>
<ul>
  <li>Search queries are used to retrieve song and artist results from Genius via our backend API.</li>
  <li>YouTube URLs are used to identify the song title and retrieve lyrics.</li>
  <li>Audio is transcribed on-device and the resulting text is used to display and analyze lyrics within the App.</li>
  <li>Lyric analysis is performed by sending selected lyric text to our backend API, which forwards it to Anthropic's Claude API. No personal identifying information is included in these requests.</li>
</ul>
<p>We do not sell, rent, trade, or share your information with third parties for marketing, advertising, or any commercial purpose.</p>

<hr>

<h2>3. Third-Party Services</h2>

<h3>BAŘ$ Backend API</h3>
<p>Hosted at <a href="https://barzs-backend.onrender.com">https://barzs-backend.onrender.com</a> on Render's infrastructure. This server intermediates requests to Genius and Anthropic. It does not log or store user data beyond what is necessary to complete each request.</p>

<h3>Genius API</h3>
<p>Song metadata and lyrics are sourced from Genius (genius.com). Requests include search terms and song IDs only. No personal user data is transmitted. Genius's privacy policy is available at <a href="https://genius.com/static/privacy">https://genius.com/static/privacy</a>.</p>

<h3>Anthropic Claude API</h3>
<p>Lyric analysis is powered by Claude, an AI model from Anthropic. Selected lyric text is sent to Anthropic's API for interpretation. No user identity, device information, or personal data is included in these requests. Anthropic's privacy policy is available at <a href="https://www.anthropic.com/privacy">https://www.anthropic.com/privacy</a>.</p>

<h3>YouTube oEmbed</h3>
<p>When a YouTube URL is submitted, BAŘ$ calls YouTube's public oEmbed endpoint to retrieve the video title. No authentication, cookies, or user data are sent. YouTube's privacy policy is available at <a href="https://policies.google.com/privacy">https://policies.google.com/privacy</a>.</p>

<h3>Apple SFSpeechRecognizer</h3>
<p>On-device speech recognition is provided by Apple's Speech framework. When speech recognition is active, Apple may process audio on its servers depending on the device model and iOS version. This is governed by Apple's privacy policy at <a href="https://www.apple.com/legal/privacy">https://www.apple.com/legal/privacy</a>.</p>

<hr>

<h2>4. Data Storage and Retention</h2>

<h3>On-Device Storage</h3>
<p>Saved analyses and voice preference settings are stored locally on your device using standard iOS storage (UserDefaults and app-sandboxed storage). This data never leaves your device except through your own iCloud backup settings, which are controlled entirely by Apple and your personal iCloud configuration.</p>

<h3>Server-Side Storage</h3>
<p>BAŘ$ backend servers do not maintain a user database. No accounts are created, no identifiers are assigned, and no request history is retained after a response is delivered.</p>

<hr>

<h2>5. Children's Privacy</h2>
<p>BAŘ$ is not directed at children under the age of 17. The App contains lyrics that may include explicit language, mature themes, and references to adult content consistent with the hip-hop genre. We do not knowingly collect any information from users under 17. If you believe a minor has used the App, please contact us and we will take appropriate action.</p>

<hr>

<h2>6. Data Security</h2>
<p>All communication between the App and our backend API uses HTTPS. The backend is hosted on Render's secure cloud infrastructure. We do not store passwords, payment information, or sensitive personal data of any kind. Given that no user accounts exist, there is no personal data at risk in the event of a server-side incident.</p>

<hr>

<h2>7. Your Rights</h2>
<p>Because BAŘ$ does not collect or store personal information linked to your identity, there is no user profile to access, correct, or delete. All data processed by the App is either handled entirely on your device or transmitted transiently for the sole purpose of completing your request.</p>
<p>If you have questions about data related to a specific request, or wish to raise a privacy concern, contact us at the address below and we will respond within 30 days.</p>

<hr>

<h2>8. Changes to This Policy</h2>
<p>We may update this Privacy Policy as the App evolves. When material changes are made, the Effective Date at the top of this document will be updated. Continued use of BAŘ$ after a policy update constitutes acceptance of the revised terms. We encourage you to review this policy periodically.</p>

<hr>

<h2>9. Contact</h2>
<p>For privacy questions, concerns, or requests, contact us at:</p>
<ul>
  <li><strong>Email:</strong> <a href="mailto:drumpimp@gmail.com">drumpimp@gmail.com</a></li>
  <li><strong>App:</strong> BAŘ$</li>
  <li><strong>Backend:</strong> <a href="https://barzs-backend.onrender.com">https://barzs-backend.onrender.com</a></li>
</ul>

<hr>

<p class="footer">BAŘ$. Every bar. Explained.</p>

</body>
</html>"""
    return html
