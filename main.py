from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(override=True)

from routes import analysis, lyrics, transcribe, dictionary, tts

app = FastAPI(title="BARZS Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router,   prefix="/analyze",    tags=["Analysis"])
app.include_router(lyrics.router,     prefix="/lyrics",     tags=["Lyrics"])
app.include_router(transcribe.router, prefix="/transcribe", tags=["Transcription"])
app.include_router(dictionary.router, prefix="/dictionary", tags=["Dictionary"])
app.include_router(tts.router,        prefix="/tts",        tags=["TTS"])


@app.get("/health")
async def health():
    return {"status": "BARZS backend is live"}
