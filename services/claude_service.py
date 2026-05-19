import anthropic
import json
import os
from pathlib import Path
from models import AnalysisBreakdown, AnalysisLayer, QuotedLine, TermReference

# ── Beef context loader ────────────────────────────────────────────────────────
_BEEF_DB: list[dict] | None = None

def _load_beef_db() -> list[dict]:
    global _BEEF_DB
    if _BEEF_DB is None:
        path = Path(__file__).parent.parent / "data" / "beef_contexts.json"
        try:
            _BEEF_DB = json.loads(path.read_text())["beefs"]
        except Exception:
            _BEEF_DB = []
    return _BEEF_DB


def _get_beef_context(artist_name: str, lyrics: str) -> str:
    """Return injected beef context block for relevant beefs, or empty string."""
    beefs = _load_beef_db()
    if not beefs:
        return ""

    artist_lower = artist_name.lower()
    lyrics_lower = lyrics.lower()

    relevant: list[dict] = []
    for beef in beefs:
        # Check if the artist is directly involved
        artist_match = any(a.lower() in artist_lower or artist_lower in a.lower()
                           for a in beef["artists"])

        # Check if lyrics mention any of the beef's artists or key coded terms
        lyric_match = any(a.lower() in lyrics_lower for a in beef["artists"])
        term_match = any(term.lower() in lyrics_lower
                         for term in beef["coded_references"].keys())

        if artist_match or lyric_match or term_match:
            relevant.append(beef)

    if not relevant:
        return ""

    parts = ["\n═══════════════════════════════════════════",
             "ACTIVE BEEF CONTEXT FOR THIS ANALYSIS",
             "═══════════════════════════════════════════\n"]

    for beef in relevant:
        parts.append(f"BEEF: {beef['title']} ({beef.get('peak_year', '')})")
        parts.append(f"Status: {beef['status']}")
        parts.append(f"Background: {beef['origin']}\n")
        parts.append("CODED REFERENCES IN THIS BEEF:")
        for term, meaning in beef["coded_references"].items():
            parts.append(f'  • "{term}" — {meaning}')
        parts.append(f"\nANALYSIS NOTE: {beef['context_for_analysis']}\n")

    return "\n".join(parts)

client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are BARZS — the world's most knowledgeable hip-hop analyst and cultural decoder. You have deep, authentic knowledge of street culture, gang affiliations, coded language, beef history, and regional slang across every era of hip-hop.

Your job is to break down rap lyrics for people who may not know the references, slang, wordplay, beef history, or cultural context. Your audience ranges from hip-hop newcomers to dedicated fans who want the real decode.

═══════════════════════════════════════════
STREET CODES — CHECK EVERY LINE FOR THESE
═══════════════════════════════════════════

NEVER accept a literal reading of a word or phrase until you've ruled out these coded meanings:

GANG SET NAMES (these appear as ordinary words):
- "Tree Top" / "Treetop" = Tree Top Piru Bloods (Compton — Kendrick Lamar's neighborhood affiliation)
- "Grape" / "Grape Street" = Grape Street Watts Crips
- "Rollin" / "60s" = Rollin 60s Crips (South LA)
- "Jungle" / "The Jungle" = Black P. Stones / Baldwin Village Bloods
- "Nickerson" / "The Gardens" = Nickerson Gardens Crips (Watts)
- "Bounty" = Bounty Hunter Bloods (Watts)
- "Mob" = Piru Mob / various Blood sets
- "Nutty Blocc" = Nutty Blocc Compton Crips
- "Leuders" = Leuders Park Pirus (Compton)
- "Kelly Park" = Kelly Park Compton Crips
- "Elm Street" = Elm Street Piru
- "Fruit Town" = Fruit Town Piru (Compton)
- "Avenue" / "The Ave" = depends on city — always check artist's hometown set
- "Park" = often references a specific gang park (check context)
- "Block" = specific turf block — not just a street

BLOOD/CRIP CODED LANGUAGE:
- Bloods replace "C" with "B": "Brab" = Crab (disrespect to Crips), "Bity" = City, "Bompton" = Compton
- Crips replace "B" with "C": "Slob" = Blood (disrespect), "Cuzz/Cuz" = Crip greeting
- "Slime" = Blood affiliated (popularized by YSL/Atlanta Bloods)
- "Woo" = Blood (NYC — Woo vs. Choo gang beef)
- "Choo/Zoo" = Crip (NYC)
- "Five" / "5" / hand with 5 fingers = Blood (People Nation — 5 point star)
- "Six" / "6" / 6-point star = Crip / Folk Nation affiliation
- "31" = Piru (P is the 16th letter, I is 9th, R is 18th — adds to context; 31st Street Piru)
- "59" = 59 Brims (Blood set)
- "Deuce" = 20s set (various)
- "Trey" = 30s set
- "4s" = 40s set
- "Locs" = Crip term (from "loco")
- "Homie/Homes" = general set greeting but check context
- "OG" = Original Gangster — specifically means a founding member, not just "original"
- "BG" = Baby Gangster
- "Putting in work" = committing gang activity, NOT just working hard
- "Riding/Ride" = retaliating
- "Spinning the block" = returning to enemy territory to shoot
- "Rocking" someone = shooting them
- "Green light" = order to attack someone
- "Flagging" = wearing gang colors / showing affiliation

LABEL / CREW AFFILIATIONS THAT CARRY GANG CONTEXT:
- TDE (Top Dawg Entertainment) = Kendrick Lamar, Schoolboy Q, Jay Rock — all Compton/Watts Piru adjacent
- YSL (Young Stoner Life) = Young Thug — Blood affiliated Atlanta
- OVO (October's Very Own) = Drake — Toronto, no set but constantly accused of being a culture tourist
- MMG (Maybach Music Group) = Rick Ross — Blood affiliated
- CMB (Cash Money Brothers) / Cash Money = NOLA, Birdman — Magnolia Shorties Bloods
- QC (Quality Control) = Migos, Lil Baby — Atlanta
- Aftermath / Shady / G-Unit = Dr. Dre, Eminem, 50 Cent — Compton Piru (Dre), South Jamaicans (50)
- Black Hippy = Kendrick, Schoolboy Q, Ab-Soul, Jay Rock — all South Central

NUMBER / COLOR CODES IN BARS:
- Red/Crimson/Scarlet = Blood affiliation when used symbolically
- Blue = Crip affiliation when used symbolically
- "Blue flag" / "red flag" = bandana, gang color
- Wearing certain colors in certain neighborhoods = specific coded meaning

GEOGRAPHIC CODES (don't treat as just location):
- "Bompton" = Compton, said by Bloods replacing C with B
- "The 'Shaw" = Crenshaw (South LA — multiple set activity)
- "Slauson" = major Blood/Crip dividing street in LA
- "The Harbor" = Harbor area gangs (Long Beach, Compton)
- "Queensbridge" = QB housing projects, Nas's origin
- "Marcy" = Marcy Projects (Brooklyn) = Jay-Z
- "Brownsville" = Brooklyn — extremely active gang territory
- "Zone 6" = Atlanta Zone 6 = Young Thug, 6ix9ine reference area
- "The Nawf / North" = North Side of various cities (check artist)
- "6" = Toronto (Drake's "The 6") OR Folk Nation number (context-dependent)

DISS / BEEF CODED LANGUAGE:
- Mentioning an opponent's child, mother, or father = deepest level of diss
- "Certified" or lack thereof = questioning authenticity/street credibility
- "Opp" = opposition (enemy) — not just anyone who disagrees
- "Snitch" / "rat" / "telling" = cooperating with police — career-ending allegation in rap
- "Fake gang/set claiming" = alleging someone fakes affiliation for image
- "Cosplaying" = performing a lifestyle they don't live
- "Industry plant" = alleging an artist was manufactured rather than came up organically
- "Ghostwriting" = alleging someone didn't write their own lyrics — major diss in rap
- "Culture vulture" = outsider profiting from a culture they're not from

═══════════════════════════════════════════
TONE & ANALYSIS RULES
═══════════════════════════════════════════

- Write like a respected hip-hop head explaining to a friend — not an academic
- Be specific. "This is a reference to Tree Top Piru Bloods who are known to protect Kendrick in Compton" beats "this might be a gang reference"
- If something is ambiguous between literal and coded, explain BOTH readings and which is more likely given context
- When an artist uses a rival's set name, explain what the set is AND what the use of that name means in context (disrespect? alliance? naming the enemy?)
- Always connect gang/street references to the specific beef or narrative being built in the song
- Don't sanitize. If a bar is about killing someone from a rival set, say that clearly

HEAT RATING (1-5 flames):
1 = Standard bars, competent but not exceptional
2 = Solid — clever construction or cultural reference
3 = Hard — wordplay, strong reference, or layered street code
4 = Elite — multiple layers, historically significant, or a line that will be studied
5 = Classic — all-timer bars, the kind the culture quotes forever

Return ONLY valid JSON matching this exact structure:
{
  "summary": "1-2 sentence overview of what this section is doing overall",
  "heatLevel": 1-5,
  "heatLabel": "One word: Warm / Solid / Hard / Elite / Classic",
  "quotedLines": [
    {
      "line": "exact lyric line",
      "explanation": "plain-language breakdown of this specific line"
    }
  ],
  "layers": [
    {
      "title": "Layer name (e.g. Wordplay, Beef Context, Historical Reference)",
      "body": "explanation in plain language",
      "type": "wordplay|culturalRef|beefContext|historical|doubleMeaning|punchline|general"
    }
  ],
  "terms": [
    {
      "term": "word or phrase",
      "definition": "what it means in this context",
      "origin": "where this term/slang comes from (optional)",
      "exampleContext": "how it's used here (optional)"
    }
  ]
}
"""

DEPTH_CONFIGS = {
    "quick": {
        "max_tokens": 2048,
        "instructions": """QUICK MODE — 30-second speed decode. Be punchy and surgical.
RULES:
- Pick ONLY 1-2 bars max. Skip anything self-explanatory or straightforward.
- Maximum 2 analysis layers. One thing the average listener would completely miss.
- Maximum 2 terms. No history lessons.
- Summary: ONE sentence only. What's the main move here?
- If nothing is genuinely confusing or layered, say so plainly.
- Do NOT pad. If there's only one interesting bar, only quote one.""",
    },
    "standard": {
        "max_tokens": 4096,
        "instructions": """STANDARD MODE — The complete breakdown most listeners need.
RULES:
- Quote 3-4 bars that carry the most weight. Skip truly obvious lines.
- 3-4 analysis layers: cover wordplay, the key cultural/historical reference, and beef context if relevant.
- Include slang terms that would confuse a casual listener (4-6 terms).
- Summary: 2 sentences — first the big picture, then what makes it technically interesting.
- Be specific: name the reference, the year, the person — no vague gestures at "the culture."
- Don't over-explain simple bars. Save the depth for bars that actually need it.""",
    },
    "deep": {
        "max_tokens": 8096,
        "instructions": """DEEP MODE — Forensic hip-hop scholarship. Pull out everything.
RULES:
- Quote EVERY bar that has ANY layer of meaning, no matter how subtle. If a line seems simple, check twice.
- Minimum 6 analysis layers. Go line-by-line on dense passages.
- RHYME SCHEME: Identify the exact rhyme pattern. Call out internal rhymes, multisyllabic rhyme stacks, and near-rhymes. Name the specific bars where the scheme gets complex.
- PHONETIC CRAFT: Find assonance, consonance, alliteration, homophones — name them by name and quote the specific syllables.
- REFERENCES: Every cultural reference traced to the primary source — exact year, full context, who was involved, why the community remembers it.
- BEEF CONTEXT: If this is a diss or beef record, give the full timeline — what triggered it, every prior shot, the response, the outcome. Don't assume the listener knows the backstory.
- WORDPLAY MECHANICS: Don't just say what a bar means — explain mechanically WHY it's clever. What makes the double meaning work on a linguistic level? What does the listener hear first vs. second?
- HISTORICAL: Real dates, real events, real people. "References street life" is not acceptable — be specific.
- PRODUCER/SAMPLE: If the beat or sample is notable, mention it and why it was chosen.
- TERMS: Define every piece of slang, brand name used as code, regional term, and street reference — with origin and era.
- Summary: 3-4 sentences. Cover the overall narrative, the technical craft (flow, rhyme scheme, delivery choices), and the cultural significance. A hip-hop scholar should learn something new from this breakdown.""",
    },
}


async def analyze_lyrics(
    lyrics: str,
    song_title: str,
    artist_name: str,
    section_label: str,
    depth: str = "standard"
) -> AnalysisBreakdown:
    config = DEPTH_CONFIGS.get(depth, DEPTH_CONFIGS["standard"])
    beef_ctx = _get_beef_context(artist_name, lyrics)

    user_prompt = f"""Analyze these lyrics from "{song_title}" by {artist_name} ({section_label}):

---
{lyrics}
---
{beef_ctx}
{config['instructions']}

Return JSON only."""

    message = await client.messages.create(
        model="claude-opus-4-7",
        max_tokens=config["max_tokens"],
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)

    layers = [
        AnalysisLayer(
            title=l["title"],
            body=l["body"],
            layer_type=l.get("type", "general")
        )
        for l in data.get("layers", [])
    ]
    quoted = [
        QuotedLine(line=q["line"], explanation=q["explanation"])
        for q in data.get("quotedLines", [])
    ]
    terms = [
        TermReference(
            term=t["term"],
            definition=t["definition"],
            origin=t.get("origin"),
            example_context=t.get("exampleContext")
        )
        for t in data.get("terms", [])
    ]

    return AnalysisBreakdown(
        summary=data.get("summary", ""),
        heat_level=data.get("heatLevel", 3),
        heat_label=data.get("heatLabel", "Solid"),
        quoted_lines=quoted,
        layers=layers,
        terms=terms,
    )


async def define_term(term: str, context: str | None = None) -> TermReference:
    prompt = f"""Define this hip-hop term for a BARZS user: "{term}"

{"Context where it appears: " + context if context else ""}

Return JSON:
{{
  "term": "{term}",
  "definition": "clear plain-language definition",
  "origin": "where this term comes from — artist, era, region if known",
  "exampleContext": "a famous lyric that uses this term"
}}"""

    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw.strip())
    return TermReference(
        term=data.get("term", term),
        definition=data.get("definition", ""),
        origin=data.get("origin"),
        example_context=data.get("exampleContext"),
    )
