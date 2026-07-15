from pydantic import BaseModel, Field
from typing import Optional, Union


class Legislator(BaseModel):
    id: str
    name: str
    role: str
    level: str          # "federal" | "state"
    chamber: str        # "senate" | "house"
    party: str
    state: str
    district: Optional[str] = None
    url: Optional[str] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None


class SpeakerProfile(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    state: Optional[str] = None
    age: Optional[Union[int, str]] = None


class SocialLinks(BaseModel):
    youtube: Optional[str] = None
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    linkedin: Optional[str] = None


class ScriptRequest(BaseModel):
    state: str                       # target legislator's state (abbr)
    legislator_id: str               # id from /advocacy/legislators
    application_id: str              # id from /advocacy/applications
    goal_id: str                     # id from /advocacy/goals
    minutes: float = Field(default=2, ge=1, le=10)
    user: SpeakerProfile = SpeakerProfile()
    socials: SocialLinks = SocialLinks()
