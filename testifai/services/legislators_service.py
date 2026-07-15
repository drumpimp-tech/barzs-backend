"""
Legislator data service for the TESTIFAI script app.

Pulls **live, current** legislator data so scripts can be addressed to real
officials:

  • U.S. Senators and U.S. Representatives — from the public, key-free
    unitedstates.io dataset (github.com/unitedstates/congress-legislators).
  • State legislators (state senate + state house) — from the Open States v3
    API when an OPENSTATES_API_KEY is configured. Degrades gracefully to
    federal-only when no key is present.

Everything is cached in-process so we only hit the network occasionally.
"""

import os
import time
import json
from pathlib import Path

import httpx

CONGRESS_URL = "https://theunitedstates.io/congress-legislators/legislators-current.json"
CONGRESS_PHOTO = "https://theunitedstates.io/images/congress/225x275/{bioguide}.jpg"
OPENSTATES_BASE = "https://v3.openstates.org"

_CACHE_TTL = 60 * 60 * 12  # 12 hours

# in-memory caches
_congress_cache: dict = {"fetched_at": 0.0, "by_state": {}}
_openstates_cache: dict = {}  # state_abbr -> {"fetched_at": ts, "people": [...]}

_STATES_PATH = Path(__file__).parent.parent / "data" / "us_states.json"
_STATE_NAME = {s["abbr"]: s["name"] for s in json.loads(_STATES_PATH.read_text())}

_PARTY_FULL = {
    "Democrat": "Democrat",
    "Republican": "Republican",
    "Independent": "Independent",
    "Libertarian": "Libertarian",
    "D": "Democrat",
    "R": "Republican",
    "I": "Independent",
}


def _norm_party(p: str | None) -> str:
    if not p:
        return "Unknown"
    return _PARTY_FULL.get(p, p)


# ── U.S. Congress (senators + representatives) ──────────────────────────────

async def _load_congress() -> dict:
    """Fetch and index current members of Congress by state abbreviation."""
    now = time.time()
    if _congress_cache["by_state"] and now - _congress_cache["fetched_at"] < _CACHE_TTL:
        return _congress_cache["by_state"]

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(CONGRESS_URL)
        r.raise_for_status()
        raw = r.json()

    by_state: dict[str, list[dict]] = {}
    for person in raw:
        terms = person.get("terms") or []
        if not terms:
            continue
        term = terms[-1]  # current/most recent term
        state = term.get("state")
        if not state:
            continue
        bioguide = (person.get("id") or {}).get("bioguide", "")
        name = (person.get("name") or {}).get("official_full") or " ".join(
            filter(None, [(person.get("name") or {}).get("first"),
                          (person.get("name") or {}).get("last")])
        )
        is_sen = term.get("type") == "sen"
        district = term.get("district")
        entry = {
            "id": bioguide or name,
            "name": name,
            "role": "U.S. Senator" if is_sen else "U.S. Representative",
            "level": "federal",
            "chamber": "senate" if is_sen else "house",
            "party": _norm_party(term.get("party")),
            "state": state,
            "district": None if is_sen else (str(district) if district is not None else None),
            "url": term.get("url"),
            "phone": term.get("phone"),
            "photo_url": CONGRESS_PHOTO.format(bioguide=bioguide) if bioguide else None,
        }
        by_state.setdefault(state, []).append(entry)

    _congress_cache["by_state"] = by_state
    _congress_cache["fetched_at"] = now
    return by_state


# ── State legislators (Open States, optional) ───────────────────────────────

async def _load_state_legislators(state_abbr: str) -> list[dict]:
    """Fetch state senate + house members via Open States v3 (needs API key)."""
    api_key = os.environ.get("OPENSTATES_API_KEY", "").strip()
    if not api_key:
        return []

    cached = _openstates_cache.get(state_abbr)
    now = time.time()
    if cached and now - cached["fetched_at"] < _CACHE_TTL:
        return cached["people"]

    jurisdiction = _STATE_NAME.get(state_abbr)
    if not jurisdiction:
        return []

    people: list[dict] = []
    headers = {"X-API-KEY": api_key}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            page = 1
            max_pages = 8  # cap: up to ~400 people, covers every chamber
            while page <= max_pages:
                r = await client.get(
                    f"{OPENSTATES_BASE}/people",
                    headers=headers,
                    params={
                        "jurisdiction": jurisdiction,
                        "org_classification": "legislature",
                        "per_page": 50,
                        "page": page,
                    },
                )
                if r.status_code != 200:
                    break
                payload = r.json()
                for p in payload.get("results", []):
                    role = p.get("current_role") or {}
                    org = role.get("org_classification") or ""
                    is_upper = org == "upper"
                    people.append({
                        "id": p.get("id") or p.get("name"),
                        "name": p.get("name"),
                        "role": role.get("title") or ("State Senator" if is_upper else "State Representative"),
                        "level": "state",
                        "chamber": "senate" if is_upper else "house",
                        "party": _norm_party(p.get("party")),
                        "state": state_abbr,
                        "district": str(role.get("district")) if role.get("district") is not None else None,
                        "url": p.get("openstates_url"),
                        "phone": None,
                        "photo_url": p.get("image") or None,
                    })
                pagination = payload.get("pagination") or {}
                if page >= (pagination.get("max_page") or page):
                    break
                page += 1
    except Exception:
        # Network / rate-limit issues shouldn't break the whole request.
        return cached["people"] if cached else []

    _openstates_cache[state_abbr] = {"fetched_at": now, "people": people}
    return people


# ── Public API ──────────────────────────────────────────────────────────────

async def get_legislators(state_abbr: str, chamber: str = "all") -> list[dict]:
    """
    Return legislators for a state.

    chamber:
      "all"      → federal senators + representatives + (if available) state leg
      "senate"   → U.S. Senators + state senators
      "house"    → U.S. Representatives + state house members
      "federal"  → U.S. Senators + Representatives only
      "state"    → state legislators only (requires Open States key)
    """
    state_abbr = (state_abbr or "").upper()
    if state_abbr not in _STATE_NAME:
        raise ValueError(f"Unknown state: {state_abbr}")

    federal: list[dict] = []
    if chamber in ("all", "senate", "house", "federal"):
        by_state = await _load_congress()
        federal = list(by_state.get(state_abbr, []))

    state: list[dict] = []
    if chamber in ("all", "senate", "house", "state"):
        state = await _load_state_legislators(state_abbr)

    combined = federal + state

    if chamber == "senate":
        combined = [m for m in combined if m["chamber"] == "senate"]
    elif chamber == "house":
        combined = [m for m in combined if m["chamber"] == "house"]
    elif chamber == "federal":
        combined = [m for m in combined if m["level"] == "federal"]
    elif chamber == "state":
        combined = [m for m in combined if m["level"] == "state"]

    # Sort: senators first, then by name.
    order = {"senate": 0, "house": 1}
    combined.sort(key=lambda m: (m["level"] != "federal", order.get(m["chamber"], 2), m["name"]))
    return combined


async def get_legislator(state_abbr: str, legislator_id: str) -> dict | None:
    """Look up a single legislator by id within a state."""
    for m in await get_legislators(state_abbr, "all"):
        if m["id"] == legislator_id:
            return m
    return None
