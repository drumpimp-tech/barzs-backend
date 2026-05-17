import os
import re
import asyncio
import httpx
import lyricsgenius
from urllib.parse import urlparse, urlunparse
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


def _extract_year(date_str: str | None) -> int | None:
    """Pull a 4-digit year out of any Genius date string, or return None."""
    if not date_str:
        return None
    m = re.search(r"\b(19|20)\d{2}\b", date_str)
    return int(m.group()) if m else None


async def get_artist_albums(artist_id: int) -> list[Album]:
    """
    Fetch songs and group them into albums by cover art URL.
    Same art = same album/project. Falls back to year for art-less songs.
    Fetches up to 30 pages (1,500 songs) and filters to 1980+.
    """
    all_songs: list[Song] = []
    page = 1
    async with httpx.AsyncClient() as client:
        while page <= 30:
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
                release = s.get("release_date_for_display")
                year = _extract_year(release)
                if year is not None and year < 1980:
                    continue
                all_songs.append(Song(
                    id=s.get("id", 0),
                    title=s.get("title", ""),
                    artist_name=s.get("primary_artist", {}).get("name", ""),
                    cover_url=s.get("song_art_image_url"),
                    release_date=release,
                    genius_url=s.get("url"),
                ))
            if not data.get("next_page"):
                break
            page += 1

    def _norm(url: str | None) -> str | None:
        if not url:
            return None
        p = urlparse(url)
        return urlunparse(p._replace(query="", fragment=""))

    def _group_key(song: Song) -> str:
        # Group by cover art — same art means same album/project.
        # Fall back to year so undated/art-less songs cluster by era rather than
        # each becoming their own entry.
        art = _norm(song.cover_url)
        if art:
            return art
        year = _extract_year(song.release_date)
        return f"year::{year}" if year else f"single::{song.id}"

    groups: dict[str, list[Song]] = {}
    group_order: list[str] = []
    for song in all_songs:
        key = _group_key(song)
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(song)

    # Build pseudo-Album objects — newest first (API returns newest first)
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

    # lyrics.ovh: free API, no Cloudflare blocking on cloud servers
    raw_lyrics = await _fetch_lyrics_ovh(song.artist_name, song.title)

    # Fallback: Genius referents API (official token-gated, not Cloudflare blocked)
    if not raw_lyrics:
        raw_lyrics = await _fetch_lyrics_referents(song_id)

    sections = parse_lyrics_to_sections(raw_lyrics)
    return song, sections


def _clean_for_lyrics_ovh(s: str) -> str:
    """Normalize a title/artist for lyrics.ovh — strip apostrophes, features, parens."""
    # Remove feat. / ft. / featuring suffix
    s = re.sub(r'\s*(feat\.?|ft\.?|featuring)\s+.*', '', s, flags=re.IGNORECASE)
    # Remove parenthetical suffixes: (Official), (Remix), (prod. X), etc.
    s = re.sub(r'\s*\(.*?\)', '', s)
    # Remove curly/square brackets
    s = re.sub(r'\s*[\[{].*?[\]}]', '', s)
    # Remove apostrophes and backticks that break URL parsing
    s = re.sub(r"[''`‘’]", '', s)
    # Collapse extra whitespace
    return ' '.join(s.split())


async def _fetch_lyrics_ovh(artist: str, title: str) -> str:
    """Fetch full lyrics from lyrics.ovh (cloud-friendly, no Cloudflare)."""
    from urllib.parse import quote
    artist_clean = _clean_for_lyrics_ovh(artist)
    title_clean = _clean_for_lyrics_ovh(title)
    url = f"https://api.lyrics.ovh/v1/{quote(artist_clean)}/{quote(title_clean)}"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(url)
            if r.status_code == 200:
                lyrics = r.json().get("lyrics", "").strip()
                # lyrics.ovh sometimes returns "\n\n" as the whole body for missing songs
                if len(lyrics) > 20:
                    return lyrics
    except Exception:
        pass
    return ""


async def _fetch_lyrics_referents(song_id: int) -> str:
    """Fallback: pull lyric fragments from Genius referents API (token-gated, not scraping)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{GENIUS_BASE}/referents",
                headers=HEADERS,
                params={"song_id": song_id, "text_format": "plain", "per_page": 50},
            )
            if r.status_code != 200:
                return ""
            referents = r.json()["response"]["referents"]

        fragments = []
        for ref in referents:
            fragment = ref.get("fragment", "").strip()
            if fragment:
                fragments.append(fragment)
        return "\n".join(fragments)
    except Exception:
        return ""


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
