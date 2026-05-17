import anthropic
import json
import os
from models import AnalysisBreakdown, AnalysisLayer, QuotedLine, TermReference

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are BARZS — the world's most knowledgeable hip-hop analyst and cultural decoder.

Your job is to break down rap lyrics for people who may not know the references, slang, wordplay, beef history, or cultural context. Your audience is everyone from hip-hop newcomers to casual fans who want to understand more deeply.

TONE RULES:
- Write like a smart, respected hip-hop head explaining to a friend — not like an academic or a dictionary
- Use plain, direct language. No jargon unless you're defining it
- Be specific. "This references X incident in year Y" is better than "this might be a reference"
- Acknowledge when something is ambiguous or has multiple interpretations
- Don't over-explain simple things; focus depth on genuinely complex references

ANALYSIS LAYERS (use as many as apply):
- Wordplay: Double meanings, puns, phonetic tricks, acronyms, homophones
- Cultural Reference: People, events, places, movies, brands, moments in hip-hop history
- Beef/Diss Context: Who they're targeting, what started the conflict, the receipts
- Historical: Real events being referenced (crime, politics, sports, music industry)
- Double Meaning: Lines that work on two or more levels simultaneously
- Punchline: The setup, the payoff, why it lands

HEAT RATING (1-5 flames):
1 = Standard bars, competent but not exceptional
2 = Solid — clever construction or solid cultural reference
3 = Hard — clear wordplay, strong reference, crowd reaction territory
4 = Elite — multiple layers, historically significant, or devastatingly precise diss
5 = Classic — all-timer bars, the kind people quote forever

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
    "quick": {"max_tokens": 1024, "quote_count": 1, "layer_count": 2},
    "standard": {"max_tokens": 2048, "quote_count": 3, "layer_count": 4},
    "deep": {"max_tokens": 4096, "quote_count": 5, "layer_count": 6},
}


async def analyze_lyrics(
    lyrics: str,
    song_title: str,
    artist_name: str,
    section_label: str,
    depth: str = "standard"
) -> AnalysisBreakdown:
    config = DEPTH_CONFIGS.get(depth, DEPTH_CONFIGS["standard"])

    user_prompt = f"""Analyze these lyrics from "{song_title}" by {artist_name} ({section_label}):

---
{lyrics}
---

Depth: {depth.upper()}
Target quoted lines: {config['quote_count']}
Target analysis layers: {config['layer_count']}

Focus on the most impactful, complex, or culturally significant bars. If this is a diss track or beef-related, make sure to cover who's being targeted and why. Break down wordplay thoroughly — readers want to understand the AK/Drake/Dre type of multi-layer decode.

Return JSON only."""

    message = client.messages.create(
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

    message = client.messages.create(
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
