from fastapi import APIRouter, HTTPException
from models import AnalysisRequest, AnalysisBreakdown, TermReference
from services import claude_service

router = APIRouter()


@router.post("", response_model=dict)
async def analyze(request: AnalysisRequest):
    try:
        breakdown = await claude_service.analyze_lyrics(
            lyrics=request.lyrics,
            song_title=request.song_title,
            artist_name=request.artist_name,
            section_label=request.section_label,
            depth=request.analysis_depth,
        )
        return {"breakdown": breakdown.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/define", response_model=TermReference)
async def define_term(body: dict):
    term = body.get("term", "")
    context = body.get("context")
    if not term:
        raise HTTPException(status_code=400, detail="term is required")
    try:
        result = await claude_service.define_term(term, context)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
