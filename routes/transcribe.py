from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()


@router.post("/audio", response_model=dict)
async def transcribe_audio(file: UploadFile = File(...)):
    allowed = {"audio/mpeg", "audio/wav", "audio/aac", "audio/mp4", "application/octet-stream"}
    if file.content_type and file.content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    try:
        contents = await file.read()
        from services.whisper_service import transcribe_audio
        result = await transcribe_audio(contents, file.filename or "audio.mp3")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
