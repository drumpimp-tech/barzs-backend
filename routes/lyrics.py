from fastapi import APIRouter, HTTPException, Query
from models import Song, Artist, Album
from services import genius_service

router = APIRouter()


@router.get("/search", response_model=list[Song])
async def search(q: str):
    if not q:
        raise HTTPException(status_code=400, detail="query required")
    try:
        return await genius_service.search_songs(q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/artist", response_model=Artist)
async def get_artist(name: str):
    try:
        return await genius_service.get_artist(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/artist/{artist_id}/latest", response_model=list[Song])
async def get_artist_latest(artist_id: int):
    """Fast endpoint — returns flat list of latest songs directly by artist ID."""
    try:
        return await genius_service.get_artist_latest_songs(artist_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/albums/{artist_id}", response_model=list[Album])
async def get_albums(artist_id: int, max_pages: int = Query(default=3, ge=1, le=10)):
    try:
        return await genius_service.get_artist_albums(artist_id, max_pages=max_pages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/album/{album_id}/songs", response_model=list[Song])
async def get_album_songs(album_id: int):
    try:
        return await genius_service.get_album_songs(album_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/song/{song_id}", response_model=dict)
async def get_song(song_id: int):
    try:
        song, sections = await genius_service.get_song_with_lyrics(song_id)
        return {"song": song.model_dump(), "sections": [s.model_dump() for s in sections]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/youtube", response_model=dict)
async def from_youtube(body: dict):
    url = body.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="url required")
    try:
        from services.whisper_service import fetch_lyrics_from_youtube
        return await fetch_lyrics_from_youtube(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
