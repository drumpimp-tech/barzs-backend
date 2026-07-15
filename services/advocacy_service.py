"""
TESTIFAI script generation service.

Takes a target legislator, an AI application, an advocacy goal, the user's
profile, a desired length, and (optionally) the user's public social links,
and writes a personalized, ready-to-read testimony script via Claude.
"""

import os
import re
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


SYSTEM_PROMPT = """You write first-person testimony that a real person reads out \
loud to their elected official about artificial intelligence. The speaker points \
a camera at themselves, or stands at a town hall, or calls their rep, and says \
these exact words. It has to sound like THEM, not like a machine wrote it.

HARD RULES:
1. NEVER use an em dash or en dash. No "--". Use a comma, a period, or start a \
new sentence. This is non-negotiable.
2. Do not sound like AI. Banned tells: "It's not just X, it's Y." "In today's \
world / In an era of." "delve", "tapestry", "testament to", "navigate the \
landscape", "at the end of the day", "moreover", "furthermore", "unlock", \
"empower", "harness", "foster", "vibrant", "ever-evolving", "double-edged \
sword", "game-changer", stacked lists of three adjectives, and neat little \
"on one hand / on the other hand" balance. If a sentence sounds like a press \
release or a LinkedIn post, rewrite it.
3. Write the way people actually talk. Use contractions. Short sentences. Let \
some sentences be five words. Say plain things plainly. Name real, concrete \
stuff, not vague uplift.

VOICE:
- First person, direct address to the legislator by name.
- Grounded in the speaker's own life, work, and community (use their profile and \
their creator presence when given, but never invent facts about them).
- Focused on ONE AI use and ONE goal. Don't drift.
- Honest. You can admit a worry, then say why you still believe in it. No \
partisan attacks, no insults, no made-up statistics.

SHAPE (do not label these out loud, just write them):
- Open by naming the official and yourself in one plain breath.
- Say why this is personal to you, fast, with a real detail.
- Make the case for this one AI use and this one goal, with a concrete example \
anyone can picture.
- Make one clear, reasonable ask of this official.
- Close with a line that sticks, and a thank you.

Return ONLY the spoken words. No headings, no stage directions, no notes about \
length, no quotation marks around the whole thing. Just what the speaker says."""


def _strip_em_dashes(text: str) -> str:
    """Guarantee no em/en dashes survive, whatever the model does."""
    # em dash, en dash, horizontal bar, and the "--" typographic stand-in.
    text = re.sub(r"\s*(?:--+|[—–―])\s*", ", ", text)
    # Clean up artifacts like ", ," or ", ." the substitution can create.
    text = re.sub(r",\s*([,.;:!?])", r"\1", text)
    text = re.sub(r"\bI,\s*([a-z])", r"I \1", text)  # avoid "I, m" style glitches
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


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
        f"{legislator.get('name')}, {legislator.get('role')}"
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

    user_prompt = f"""Write spoken testimony the speaker reads out loud.

WHO THEY ARE TALKING TO (address this person directly and respectfully):
{leg_line}

WHO IS SPEAKING:
{profile}

{creator_block or "SPEAKER'S PUBLIC PRESENCE: (none provided)"}

THE ONE AI USE THIS IS ABOUT:
{application.get('name')}: {application.get('blurb')}

THE ONE GOAL:
{goal.get('name')}: {goal.get('blurb')}

LENGTH:
About {minutes:g} minute(s) out loud, roughly {target_words} words. Hit that \
length closely. Do not go far over or under.

Make it personal to the speaker, specific to {legislator.get('state')} and to \
{legislator.get('name')}, focused only on {application.get('name')} and the goal \
of {goal.get('name')}. Remember the hard rules: no em dashes, and it must not \
sound like AI wrote it. Return ONLY the spoken words."""

    message = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    script = _strip_em_dashes(message.content[0].text.strip())
    word_count = len(script.split())

    title = (
        f"TESTIFAI: {application.get('name')} for {legislator.get('name')} "
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
