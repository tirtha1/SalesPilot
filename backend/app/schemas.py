from __future__ import annotations
from datetime import date as Date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ContactOut(APIModel):
    id: int
    customer_id: int
    name: str
    designation: str | None = None
    email: str | None = None
    phone: str | None = None


class CustomerListItem(APIModel):
    id: int
    name: str
    industry: str
    location: str | None = None
    email: str | None = None


class CustomerOut(CustomerListItem):
    phone: str | None = None
    contacts: list[ContactOut] = []
    created_at: datetime
    updated_at: datetime


class OpportunityOut(APIModel):
    id: int
    customer_id: int
    name: str
    description: str | None = None
    value: Decimal
    currency: str
    stage: str
    probability: int
    expected_close_date: Date | None = None
    competitor: str | None = None


class OpportunityPatch(BaseModel):
    stage: str | None = Field(default=None, max_length=50)
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: Date | None = None
    competitor: str | None = Field(default=None, max_length=160)


class ActionItemOut(APIModel):
    id: int
    meeting_id: int | None = None
    customer_id: int
    task: str
    due_date: Date | None = None
    status: str
    priority: str
    created_at: datetime
    updated_at: datetime


class ActionItemCreate(BaseModel):
    customer_id: int
    meeting_id: int | None = None
    task: str = Field(min_length=2, max_length=2000)
    due_date: Date | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class ActionItemPatch(BaseModel):
    task: str | None = Field(default=None, min_length=2, max_length=2000)
    due_date: Date | None = None
    status: Literal["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"] | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH"] | None = None


class InsightOut(APIModel):
    id: int
    type: str
    content: str


class MeetingOut(APIModel):
    id: int
    customer_id: int
    contact_id: int | None = None
    meeting_date: datetime
    title: str
    transcript: str | None = None
    summary: str
    sentiment: str | None = None
    created_at: datetime
    updated_at: datetime
    insights: list[InsightOut] = []
    action_items: list[ActionItemOut] = []


class MeetingCreate(BaseModel):
    customer_id: int
    contact_id: int | None = None
    meeting_date: datetime
    title: str = Field(min_length=2, max_length=240)
    transcript: str | None = Field(default=None, max_length=30000)
    summary: str = Field(min_length=2, max_length=10000)
    sentiment: str | None = Field(default=None, max_length=30)


class Candidate(APIModel):
    id: int
    name: str


class MatchResult(BaseModel):
    match_status: Literal["MATCHED", "AMBIGUOUS", "UNKNOWN"]
    customer: Candidate | None = None
    candidates: list[Candidate] = []
    confidence: float = Field(ge=0, le=1)


class ExtractedActionItem(BaseModel):
    task: str = Field(min_length=1, max_length=2000)
    due_date: Date | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class FollowUp(BaseModel):
    required: bool = False
    date: Date | None = None
    clarification_needed: bool = False


class Confidence(BaseModel):
    customer: float = Field(default=0, ge=0, le=1)
    contact: float = Field(default=0, ge=0, le=1)
    overall: float = Field(default=0, ge=0, le=1)


class MeetingAnalysis(BaseModel):
    customer_name: str | None = None
    contact_name: str | None = None
    meeting_date: Date | None = None
    summary: str | None = None
    requirements: list[str] = []
    pain_points: list[str] = []
    customer_concerns: list[str] = []
    competitors: list[str] = []
    opportunities: list[str] = []
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED"] | None = None
    action_items: list[ExtractedActionItem] = []
    follow_up: FollowUp = Field(default_factory=FollowUp)
    confidence: Confidence = Field(default_factory=Confidence)


class MeetingAnalysisRequest(BaseModel):
    transcript: str = Field(min_length=4, max_length=30000)
    meeting_date: Date | None = None


class MeetingAnalysisResponse(BaseModel):
    analysis: MeetingAnalysis
    match: MatchResult
    source: Literal["openai", "local_demo"]


class MeetingConfirmRequest(BaseModel):
    customer_id: int
    contact_id: int | None = None
    meeting_date: datetime
    title: str = Field(default="Customer meeting", min_length=2, max_length=240)
    transcript: str = Field(min_length=4, max_length=30000)
    analysis: MeetingAnalysis


class CustomerHistory(BaseModel):
    customer: CustomerOut
    meetings: list[MeetingOut]
    opportunities: list[OpportunityOut]
    action_items: list[ActionItemOut]


class CustomerBrief(BaseModel):
    customer_overview: str
    relationship_summary: str
    recent_discussions: list[str]
    open_opportunities: list[str]
    requirements: list[str]
    pain_points: list[str]
    competitors: list[str]
    outstanding_actions: list[str]
    payment_activity_summary: str
    risks: list[str]
    recommended_talking_points: list[str]
    recommended_questions: list[str]
    source: Literal["openai", "local_demo"]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=3000)


class Citation(BaseModel):
    customer_id: int | None = None
    customer_name: str | None = None
    record_type: Literal["CUSTOMER", "MEETING", "ACTION_ITEM", "OPPORTUNITY", "ACTIVITY"]
    record_id: int | None = None
    detail: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    source: Literal["openai_tools", "local_database"]


class TranscriptionResponse(BaseModel):
    transcript: str
    source: Literal["openai"]


class DashboardOut(BaseModel):
    today_follow_ups: list[ActionItemOut]
    overdue_actions: list[ActionItemOut]
    open_opportunities: list[OpportunityOut]
    recent_meetings: list[MeetingOut]
