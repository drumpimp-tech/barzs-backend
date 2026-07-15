from pydantic import BaseModel, Field
from typing import Optional, Union, Any
from uuid import uuid4, UUID


class LyricLine(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    number: int
    text: str


class LyricSection(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    label: str
    lines: list[LyricLine]
    is_selected: bool = False


class Song(BaseModel):
    id: int
    title: str
    artist_name: str
    artist_id: Optional[int] = None
    album_name: Optional[str] = None
    cover_url: Optional[str] = None
    release_date: Optional[str] = None
    genius_url: Optional[str] = None
    lyrics: Optional[str] = None


class Album(BaseModel):
    id: int
    name: str
    cover_url: Optional[str] = None
    release_date: Optional[str] = None
    songs: list[Song] = []


class Artist(BaseModel):
    id: int
    name: str
    image_url: Optional[str] = None
    header_image_url: Optional[str] = None
    bio: Optional[str] = None
    followers_count: Optional[int] = None
    albums: list[Album] = []


class TermReference(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    term: str
    definition: str
    origin: Optional[str] = None
    example_context: Optional[str] = None


class QuotedLine(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    line: str
    explanation: str


class AnalysisLayer(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    body: str
    layer_type: str = "general"


class AnalysisBreakdown(BaseModel):
    summary: str
    heat_level: int = Field(ge=1, le=5, default=3)
    heat_label: str = "Solid"
    quoted_lines: list[QuotedLine] = []
    layers: list[AnalysisLayer] = []
    terms: list[TermReference] = []


class AnalysisRequest(BaseModel):
    lyrics: str
    song_title: str
    artist_name: str
    section_label: str
    analysis_depth: str = "standard"


class DictionaryTerm(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    term: str
    definition: str
    origin: Optional[str] = None
    region: Optional[str] = None
    era: Optional[str] = None
    category: str = "general"
    example_lines: list[str] = []
    related_terms: list[str] = []
