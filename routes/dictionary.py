import json
import os
from fastapi import APIRouter, HTTPException
from models import DictionaryTerm, TermReference
from services import claude_service

router = APIRouter()

DICT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rap_dictionary.json")


def load_dictionary() -> list[DictionaryTerm]:
    with open(DICT_PATH, "r") as f:
        data = json.load(f)
    return [DictionaryTerm(**item) for item in data]


@router.get("", response_model=list[DictionaryTerm])
async def get_dictionary():
    try:
        return load_dictionary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/define", response_model=TermReference)
async def define_term(body: dict):
    term = body.get("term", "")
    context = body.get("context")
    if not term:
        raise HTTPException(status_code=400, detail="term is required")

    # First check local dictionary
    try:
        dictionary = load_dictionary()
        match = next(
            (t for t in dictionary if t.term.lower() == term.lower()),
            None
        )
        if match:
            return TermReference(
                term=match.term,
                definition=match.definition,
                origin=match.origin,
                example_context=match.example_lines[0] if match.example_lines else None,
            )
    except Exception:
        pass

    # Fall back to Claude for unknown terms
    try:
        return await claude_service.define_term(term, context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
