import whisper
import tempfile
import os
from pathlib import Path
from services.genius_service import search_songs, parse_lyrics_to_sections
from models import LyricSection

_model = None


def get_model():
    global _model
    if _model is None:
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
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title", "")
    uploader = info.get("uploader", "")

    # Try to pull actual lyrics from Genius using the video title
    query = title
    songs = await search_songs(query)

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
