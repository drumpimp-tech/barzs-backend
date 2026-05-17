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

    # Strip common YouTube noise from the title before searching Genius
    clean_title = re.sub(
        r'\s*[\(\[]\s*(official\s*(video|audio|music\s*video|lyric\s*video)?|'
        r'lyrics?|4k|hd|remaster(ed)?|ft\.?.*|feat\.?.*|prod\.?.*|dir\.?.*|'
        r'explicit|clean)\s*[\)\]]\s*',
        ' ', title, flags=re.IGNORECASE
    ).strip()

    songs = await search_songs(clean_title)

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
