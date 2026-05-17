import tempfile
import os
from pathlib import Path
from services.genius_service import search_songs, parse_lyrics_to_sections
from models import LyricSection

_model = None


def get_model():
    global _model
    if _model is None:
        import whisper
        _model = whisper.load_model("base")  # upgrade to "medium" for better accuracy
    return _model


async def transcribe_audio(file_bytes: bytes, filename: str) -> dict:
    suffix = Path(filename).suffix or ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        model = get_model()
        result = model.transcribe(tmp_path, language="en", task="transcribe")
        transcript = result["text"].strip()
        sections = parse_lyrics_to_sections(transcript)

        # Try to detect artist/title from filename
        detected_title = None
        detected_artist = None
        stem = Path(filename).stem
        if " - " in stem:
            parts = stem.split(" - ", 1)
            detected_artist = parts[0].strip()
            detected_title = parts[1].strip()
        elif "_" in stem:
            detected_title = stem.replace("_", " ")

        return {
            "transcript": transcript,
            "detected_title": detected_title,
            "detected_artist": detected_artist,
            "sections": [s.model_dump() for s in sections],
        }
    finally:
        os.unlink(tmp_path)


def _build_genius_query(title: str) -> str:
    import re
    # If title has "Artist - Song" format, split and clean each part separately
    if " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        song = parts[1].strip()
    else:
        artist = ""
        song = title.strip()

    # Strip featured artists from song part ("Feat ...", "ft. ...", "with ...")
    song = re.sub(r'\s+(feat\.?|ft\.?|featuring|with)\s+.+', '', song, flags=re.IGNORECASE)
    # Strip trailing noise words outside parens ("dirty", "clean", "explicit", "audio", "video")
    song = re.sub(r'\s+(dirty|clean|explicit|audio|video|official|live|acoustic|remix)$', '', song, flags=re.IGNORECASE)
    # Strip anything in parentheses or brackets
    song = re.sub(r'\s*[\(\[].*?[\)\]]', '', song).strip()

    if artist:
        return f"{artist} {song}".strip()
    return song.strip()


async def fetch_lyrics_from_youtube(url: str) -> dict:
    import re
    import httpx

    # YouTube oEmbed — free, no auth, not blocked by cloud server IPs
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
        )
        if r.status_code != 200:
            raise ValueError(f"Could not fetch video info (status {r.status_code}). Check the URL and try again.")
        data = r.json()

    title = data.get("title", "")
    uploader = data.get("author_name", "")

    search_query = _build_genius_query(title)
    songs = await search_songs(search_query)

    # If no results, fall back to shorter query (just first two words of each part)
    if not songs and " - " in title:
        parts = title.split(" - ", 1)
        fallback = f"{parts[0].strip()} {parts[1].split()[0] if parts[1].split() else ''}".strip()
        songs = await search_songs(fallback)

    if songs:
        from services.genius_service import get_song_with_lyrics
        song, sections = await get_song_with_lyrics(songs[0].id)
        return {
            "song": song.model_dump(),
            "sections": [s.model_dump() for s in sections],
        }

    # Fallback: just return metadata, no lyrics
    from models import Song
    fallback_song = Song(id=0, title=title, artist_name=uploader)
    empty_section = LyricSection(label="Lyrics not found", lines=[])
    return {
        "song": fallback_song.model_dump(),
        "sections": [empty_section.model_dump()],
    }
