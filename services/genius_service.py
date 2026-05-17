import os
import re
import asyncio
import httpx
import lyricsgenius
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup
from models import Song, Album, Artist, LyricSection, LyricLine

GENIUS_BASE = "https://api.genius.com"
TOKEN = os.environ.get("GENIUS_ACCESS_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

_genius_client = None

def _get_genius_client() -> lyricsgenius.Genius:
    global _genius_client
    if _genius_client is None:
        _genius_client = lyricsgenius.Genius(
            TOKEN,
            timeout=30,
            remove_section_headers=False,
            skip_non_songs=True,
        )
    return _genius_client


async def search_songs(query: str) -> list[Song]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GENIUS_BASE}/search", headers=HEADERS, params={"q": query})
        r.raise_for_status()
        hits = r.json()["response"]["hits"]

    songs = []
    for hit in hits[:10]:
        result = hit.get("result", {})
        songs.append(Song(
            id=result.get("id", 0),
            title=result.get("title", ""),
            artist_name=result.get("primary_artist", {}).get("name", ""),
            album_name=result.get("album", {}).get("name") if result.get("album") else None,
            cover_url=result.get("song_art_image_url"),
            release_date=result.get("release_date"),
            genius_url=result.get("url"),
        ))
    return songs


async def get_artist(name: str) -> Artist:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GENIUS_BASE}/search", headers=HEADERS, params={"q": name})
        r.raise_for_status()
        hits = r.json()["response"]["hits"]

    for hit in hits:
        artist_data = hit.get("result", {}).get("primary_artist", {})
        if artist_data and artist_data.get("name", "").lower() == name.lower():
            artist_id = artist_data.get("id")
            return await get_artist_by_id(artist_id)

    # fallback: return first artist found
    if hits:
        artist_data = hits[0].get("result", {}).get("primary_artist", {})
        return await get_artist_by_id(artist_data.get("id"))

    raise ValueError(f"Artist not found: {name}")


async def get_artist_by_id(artist_id: int) -> Artist:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GENIUS_BASE}/artists/{artist_id}", headers=HEADERS)
        r.raise_for_status()
        data = r.json()["response"]["artist"]

    return Artist(
        id=data.get("id"),
        name=data.get("name", ""),
        image_url=data.get("image_url"),
        header_image_url=data.get("header_image_url"),
        bio=data.get("description", {}).get("plain") if data.get("description") else None,
        followers_count=data.get("followers_count"),
    )


async def get_artist_albums(artist_id: int) -> list[Album]:
    """
    Genius /albums endpoint is restricted. Instead fetch songs sorted by
    release_date and group them into pseudo-albums by cover art + date.
    This surfaces the newest releases first.
    """
    all_songs: list[Song] = []
    page = 1
    async with httpx.AsyncClient() as client:
        while page <= 20:  # up to 1,000 songs (20 pages × 50) — covers 10-15 yrs
            r = await client.get(
                f"{GENIUS_BASE}/artists/{artist_id}/songs",
                headers=HEADERS,
                params={"sort": "release_date", "per_page": 50, "page": page},
            )
            if r.status_code != 200:
                break
            data = r.json()["response"]
            batch = data.get("songs", [])
            if not batch:
                break
            for s in batch:
                all_songs.append(Song(
                    id=s.get("id", 0),
                    title=s.get("title", ""),
                    artist_name=s.get("primary_artist", {}).get("name", ""),
                    cover_url=s.get("song_art_image_url"),
                    release_date=s.get("release_date_for_display"),
                    genius_url=s.get("url"),
                ))
            if not data.get("next_page"):
                break
            page += 1

    # Grouping strategy:
    # 1. If the song has a specific release date (e.g. "May 15, 2026"), group by date —
    #    new albums often get uploaded with different per-track artwork, so cover_url
    #    alone splits one album into many fake albums.
    # 2. Fall back to normalized cover_url for older songs that only have a year ("2019")
    #    or no date at all, where date-grouping would merge unrelated songs.
    def _norm(url: str | None) -> str | None:
        if not url:
            return None
        p = urlparse(url)
        return urlunparse(p._replace(query="", fragment=""))

    def _group_key(song: Song) -> str:
        date = song.release_date or ""
        # Specific date: "May 15, 2026" or "2026-05-15" — use date as key
        if date and re.search(r"(\w+ \d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2})", date):
            return f"date::{date}"
        # Year-only or no date — fall back to cover art
        return _norm(song.cover_url) or f"no_cover::{date or song.id}"

    groups: dict[str, list[Song]] = {}
    group_order: list[str] = []  # tracks insertion order
    for song in all_songs:
        key = _group_key(song)
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(song)

    # Build pseudo-Album objects in API order (newest first)
    albums: list[Album] = []
    fake_id = 900_000_000
    for key in group_order:
        songs = groups[key]
        first = songs[0]
        release = first.release_date or "New Release"
        name = f"{first.artist_name} — {release}"
        albums.append(Album(
            id=fake_id,
            name=name,
            cover_url=first.cover_url,
            release_date=first.release_date,
            songs=songs,
        ))
        fake_id += 1

    return albums


async def get_album_songs(album_id: int) -> list[Song]:
    """Fallback: fetch any song from an album via the tracks endpoint if available."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GENIUS_BASE}/albums/{album_id}/tracks", headers=HEADERS)
        if r.status_code != 200:
            return []
        tracks = r.json()["response"]["tracks"]

    songs = []
    for track in tracks:
        song = track.get("song", {})
        songs.append(Song(
            id=song.get("id"),
            title=song.get("title", ""),
            artist_name=song.get("primary_artist", {}).get("name", ""),
            cover_url=song.get("song_art_image_url"),
            genius_url=song.get("url"),
        ))
    return songs


async def get_song_with_lyrics(song_id: int) -> tuple[Song, list[LyricSection]]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GENIUS_BASE}/songs/{song_id}", headers=HEADERS)
        r.raise_for_status()
        data = r.json()["response"]["song"]

    song = Song(
        id=data.get("id"),
        title=data.get("title", ""),
        artist_name=data.get("primary_artist", {}).get("name", ""),
        album_name=data.get("album", {}).get("name") if data.get("album") else None,
        cover_url=data.get("song_art_image_url"),
        release_date=data.get("release_date"),
        genius_url=data.get("url"),
    )

    genius_url = data.get("url", "")
    raw_lyrics = await _scrape_lyrics_from_url(genius_url) if genius_url else ""
    sections = parse_lyrics_to_sections(raw_lyrics)

    return song, sections


async def _fetch_lyrics_via_client(song_id: int, title: str, artist: str) -> str:
    """Fetch lyrics by scraping the Genius HTML page with browser headers."""
    # Get the song URL from the API first
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{GENIUS_BASE}/songs/{song_id}", headers=HEADERS)
            r.raise_for_status()
            genius_url = r.json()["response"]["song"].get("url", "")
    except Exception:
        genius_url = ""

    if not genius_url:
        return ""

    return await _scrape_lyrics_from_url(genius_url)


async def _scrape_lyrics_from_url(url: str) -> str:
    """Scrape lyrics from a Genius page URL using browser-like headers."""
    browser_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://genius.com/",
    }
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers=browser_headers)
            r.raise_for_status()
            html = r.text
    except Exception:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Genius stores lyrics in data-lyrics-container divs
    containers = soup.find_all("div", attrs={"data-lyrics-container": "true"})
    if not containers:
        return ""

    parts = []
    for container in containers:
        for br in container.find_all("br"):
            br.replace_with("\n")
        parts.append(container.get_text())

    raw = "\n".join(parts)

    # Strip everything before the first section header [...]
    # This removes the "Translations..." and "Song Title Lyrics" prefix
    first_bracket = raw.find("[")
    if first_bracket > 0:
        raw = raw[first_bracket:]

    # Collapse excessive blank lines
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    return raw


def _clean_lyricsgenius_raw(raw: str) -> str:
    """Strip the artifacts lyricsgenius adds around the actual lyrics."""
    lines = raw.split("\n")

    # lyricsgenius prepends "{Song Title} Lyrics" as the very first non-empty line.
    for i, line in enumerate(lines):
        s = line.strip()
        if s:
            if s.endswith(" Lyrics") and not s.startswith("["):
                lines = lines[i + 1:]
            break

    # lyricsgenius appends an embed footer at the end, e.g.:
    #   "2EmbedShare URLCopyEmbedCopy"  or  "Embed"
    # Strip any trailing lines that are empty or embed-related.
    while lines:
        last = re.sub(r"^\d+", "", lines[-1].strip())  # drop leading digits
        if not last or "Embed" in last or "URLCopy" in last:
            lines.pop()
        else:
            break

    return "\n".join(lines)


def parse_lyrics_to_sections(raw: str) -> list[LyricSection]:
    raw = _clean_lyricsgenius_raw(raw)

    sections = []
    current_label = "Intro"
    current_lines: list[str] = []

    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if current_lines:
                lyric_lines = [LyricLine(number=i + 1, text=l) for i, l in enumerate(current_lines)]
                sections.append(LyricSection(label=current_label, lines=lyric_lines))
            current_label = stripped[1:-1]
            current_lines = []
        elif stripped:
            current_lines.append(stripped)

    if current_lines:
        lyric_lines = [LyricLine(number=i + 1, text=l) for i, l in enumerate(current_lines)]
        sections.append(LyricSection(label=current_label, lines=lyric_lines))

    if not sections:
        non_empty = [l.strip() for l in raw.split("\n") if l.strip()]
        lyric_lines = [LyricLine(number=i + 1, text=l) for i, l in enumerate(non_empty)]
        sections.append(LyricSection(label="Full Track", lines=lyric_lines))

    return sections
