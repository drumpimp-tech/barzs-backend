"""
AI Advocacy Script generation service.

Takes a target legislator, an AI application, an advocacy goal, the user's
profile, a desired length, and (optionally) the user's public social links,
and writes a personalized, ready-to-read advocacy script via Claude.
"""

import os
import asyncio
import anthropic
import httpx
from bs4 import BeautifulSoup

client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Roughly how many words a comfortable teleprompter read covers per minute.
WORDS_PER_MINUTE = 140

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


SYSTEM_PROMPT = """You are an expert political speechwriter who specializes in \
persuasive, respectful advocacy addressed to elected officials. You write \
scripts that ordinary citizens and creators can read aloud — to camera, at a \
town hall, or in a call to their representative — to advocate for the positive, \
responsible role of artificial intelligence.

Your scripts are:
- Warm, human, and grounded in the speaker's own life and community.
- Specific to the legislator being addressed (their state, their role, their constituents).
- Focused on ONE AI application and ONE advocacy goal, without drifting.
- Honest and balanced: acknowledge real concerns while making the case.
- Free of partisan attacks, insults, or misinformation.
- Written to be SPOKEN, not read on a page: short sentences, natural rhythm, \
clear signposting, easy to say out loud.

Structure every script with:
1. A greeting that names the legislator and the speaker.
2. A personal hook — why the speaker cares (drawn from their profile and creator work).
3. The core message about the chosen AI application and goal, with a concrete example.
4. A specific, reasonable ask of the legislator.
5. A memorable closing line and thank-you.

Return ONLY the script text — no stage directions, no markdown headers, no \
word-count notes, no commentary. Write it exactly as it should be read aloud."""


def _estimate_words(minutes: float) -> int:
    return max(90, int(minutes * WORDS_PER_MINUTE))


async def _scrape_url(url: str) -> str | None:
    """Best-effort: pull the public title + description from a social/creator URL."""
    if not url or not url.strip():
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(
            timeout=8, follow_redirects=True, headers={"User-Agent": _BROWSER_UA}
        ) as http:
            r = await http.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        bits: list[str] = []
        if soup.title and soup.title.string:
            bits.append(soup.title.string.strip())
        for prop in ("og:title", "og:description", "description"):
            tag = soup.find("meta", attrs={"property": prop}) or soup.find(
                "meta", attrs={"name": prop}
            )
            if tag and tag.get("content"):
                bits.append(tag["content"].strip())
        seen: set[str] = set()
        clean = []
        for b in bits:
            if b and b not in seen:
                seen.add(b)
                clean.append(b)
        text = " — ".join(clean)
        return text[:400] if text else None
    except Exception:
        return None


async def gather_creator_context(socials: dict[str, str]) -> dict:
    """
    socials: {"youtube": url, "facebook": url, "instagram": url, "linkedin": url}
    Returns {"summaries": {platform: text}, "block": "..."} — a plain-text
    context block to feed into the script prompt.
    """
    platforms = [(k, v) for k, v in (socials or {}).items() if v]
    if not platforms:
        return {"summaries": {}, "block": ""}

    results = await asyncio.gather(*[_scrape_url(v) for _, v in platforms])
    summaries: dict[str, str] = {}
    lines: list[str] = []
    for (platform, url), summary in zip(platforms, results):
        if summary:
            summaries[platform] = summary
            lines.append(f"- {platform.title()} ({url}): {summary}")
        else:
            lines.append(f"- {platform.title()} ({url}): (provided by speaker)")

    block = ""
    if lines:
        block = (
            "SPEAKER'S PUBLIC PRESENCE (weave in naturally where it strengthens "
            "the message; do not fabricate details beyond this):\n" + "\n".join(lines)
        )
    return {"summaries": summaries, "block": block}


async def generate_script(
    *,
    legislator: dict,
    application: dict,
    goal: dict,
    user: dict,
    minutes: float,
    creator_block: str = "",
) -> dict:
    target_words = _estimate_words(minutes)

    leg_line = (
        f"{legislator.get('name')} — {legislator.get('role')}"
        + (f", District {legislator['district']}" if legislator.get("district") else "")
        + f" ({legislator.get('party')}, {legislator.get('state')})"
    )

    profile_parts = []
    if user.get("name"):
        profile_parts.append(f"Name: {user['name']}")
    if user.get("gender"):
        profile_parts.append(f"Gender: {user['gender']}")
    if user.get("age"):
        profile_parts.append(f"Age: {user['age']}")
    if user.get("state"):
        profile_parts.append(f"Home state: {user['state']}")
    profile = "; ".join(profile_parts) or "(not specified)"

    # Higher-quality model for longer scripts, faster model for short ones.
    if minutes >= 6:
        model, max_tokens = "claude-opus-4-7", 8000
    else:
        model, max_tokens = "claude-sonnet-4-6", 4000

    user_prompt = f"""Write an AI-advocacy script to be read aloud.

TARGET LEGISLATOR (address this person directly and respectfully):
{leg_line}

SPEAKER PROFILE:
{profile}

{creator_block or "SPEAKER'S PUBLIC PRESENCE: (none provided)"}

AI APPLICATION THIS SCRIPT IS ABOUT:
{application.get('name')} — {application.get('blurb')}

GOAL OF THIS SCRIPT:
{goal.get('name')} — {goal.get('blurb')}

LENGTH:
About {minutes:g} minute(s) when read aloud — roughly {target_words} words. \
Hit that length closely; do not go far over or under.

Make it personal to the speaker, specific to {legislator.get('state')} and to \
{legislator.get('name')}, focused only on {application.get('name')} and the goal \
of {goal.get('name')}. Return ONLY the spoken script text."""

    message = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    script = message.content[0].text.strip()
    word_count = len(script.split())

    title = (
        f"AI Advocacy — {application.get('name')} to {legislator.get('name')} "
        f"({legislator.get('state')})"
    )

    return {
        "title": title,
        "script": script,
        "word_count": word_count,
        "target_words": target_words,
        "estimated_minutes": round(word_count / WORDS_PER_MINUTE, 1),
        "model": model,
        "legislator": legislator,
        "application": application,
        "goal": goal,
    }
