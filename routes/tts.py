import os
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter()

EL_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
EL_BASE    = "https://api.elevenlabs.io/v1/text-to-speech"


class TTSRequest(BaseModel):
    text: str
    voice_id: str
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.3


@router.post("/speak")
async def speak(req: TTSRequest):
    """
    Call ElevenLabs server-side and stream audio bytes back to the iOS app.
    The app never touches the ElevenLabs key.
    """
    if not EL_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ElevenLabs key not configured on server. Add ELEVENLABS_API_KEY to backend/.env"
        )

    url = f"{EL_BASE}/{req.voice_id}"
    headers = {
        "xi-api-key": EL_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "text": req.text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": req.stability,
            "similarity_boost": req.similarity_boost,
            "style": req.style,
            "use_speaker_boost": True,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=headers, json=body)

    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"ElevenLabs error: {r.text}")

    return Response(content=r.content, media_type="audio/mpeg")


@router.get("/voices")
async def list_voices():
    """Return ElevenLabs voice list so the app can show names without a key."""
    if not EL_API_KEY:
        return {"voices": []}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": EL_API_KEY},
        )

    if r.status_code != 200:
        return {"voices": []}

    return r.json()
