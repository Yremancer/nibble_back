
from enum import StrEnum

from pydantic import BaseModel, Field


class ClassificationDecision(StrEnum):
    KEEP = "keep"
    DISCARD = "discard"
    REVIEW = "review"


class PostCategory(StrEnum):
    FISHING_REPORT = "fishing_report"
    INCIDENT = "incident"
    USEFUL_INFO = "useful_info"


class LocationMention(BaseModel):
    text: str
    evidence: str


class SpeciesMention(BaseModel):
    name: str
    quantity: int | None = None
    max_weight_g: int | None = None
    evidence: str


class MethodMention(BaseModel):
    name: str
    evidence: str


class ClassificationResult(BaseModel):

    decision: ClassificationDecision
    category: PostCategory | None = None
    reason: str
    is_advertisement: bool = False
    needs_media_analysis: bool = False
    summary: str | None = None
    location_mentions: list[LocationMention] = Field(default_factory=list)
    fishing_date: str | None = None
    event_date: str | None = None
    species: list[SpeciesMention] = Field(default_factory=list)
    methods: list[MethodMention] = Field(default_factory=list)
    bait: str | None = None
    conditions: str | None = None
