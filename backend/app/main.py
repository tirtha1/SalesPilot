from __future__ import annotations
from datetime import date, datetime, timezone
import logging
import time
import uuid
from contextvars import ContextVar
from logging.config import dictConfig
from pathlib import Path
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
from .ai import SalesPilotAIError, analyze_meeting, ask_salespilot, brief_customer, match_customer, transcribe_audio
from .config import get_settings
from .database import get_db
from .models import ActionItem, Contact, Customer, Meeting, MeetingInsight, Opportunity
from .schemas import (
    ActionItemCreate, ActionItemOut, ActionItemPatch, AskRequest, AskResponse, CustomerBrief,
    CustomerHistory, CustomerListItem, CustomerOut, DashboardOut, ErrorResponse, MeetingAnalysisRequest,
    MeetingAnalysisResponse, MeetingConfirmRequest, MeetingCreate, MeetingOut, OpportunityOut,
    OpportunityPatch, TranscriptionResponse,
)

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging() -> None:
    dictConfig({"version": 1, "disable_existing_loggers": False, "formatters": {"jsonish": {"format": "%(asctime)s %(levelname)s request_id=%(request_id)s %(name)s %(message)s"}}, "filters": {"request_id": {"()": RequestIdFilter}}, "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "jsonish", "filters": ["request_id"]}}, "root": {"handlers": ["stdout"], "level": "INFO"}})


configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()
app = FastAPI(title="SalesPilot API", version="1.0.0", description="Safe, human-confirmed AI sales workflow API.")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


def error_response(status: int, code: str, message: str, request_id: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "request_id": request_id or request_id_var.get()}})


@app.middleware("http")
async def observability(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info("request endpoint=%s status=%s duration_ms=%d", request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
        return response
    except Exception:
        logger.exception("unhandled_request_error endpoint=%s", request.url.path)
        return error_response(500, "INTERNAL_ERROR", "Something went wrong. Please try again.", request_id)
    finally:
        request_id_var.reset(token)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, __: RequestValidationError):
    return error_response(422, "INVALID_REQUEST", "One or more request fields are invalid.")


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    codes = {404: "NOT_FOUND", 422: "INVALID_REQUEST", 403: "FORBIDDEN"}
    return error_response(exc.status_code, codes.get(exc.status_code, "REQUEST_FAILED"), str(exc.detail))


@app.exception_handler(SalesPilotAIError)
async def ai_error(_: Request, exc: SalesPilotAIError):
    statuses = {"CUSTOMER_NOT_FOUND": 404, "OPENAI_NOT_CONFIGURED": 503}
    return error_response(statuses.get(exc.code, 502), exc.code, exc.message)


def get_customer_or_404(db: Session, customer_id: int, full: bool = False) -> Customer:
    query = select(Customer).where(Customer.id == customer_id)
    if full:
        query = query.options(selectinload(Customer.contacts), selectinload(Customer.meetings).selectinload(Meeting.insights), selectinload(Customer.opportunities), selectinload(Customer.action_items))
    customer = db.scalar(query)
    if not customer:
        raise HTTPException(404, "Customer not found")
    return customer


def get_meeting_or_404(db: Session, meeting_id: int) -> Meeting:
    meeting = db.scalar(select(Meeting).where(Meeting.id == meeting_id).options(selectinload(Meeting.insights), selectinload(Meeting.action_items)))
    if not meeting:
        raise HTTPException(404, "Meeting not found")
    return meeting


def get_action_or_404(db: Session, action_id: int) -> ActionItem:
    action = db.get(ActionItem, action_id)
    if not action:
        raise HTTPException(404, "Action item not found")
    return action


def get_opportunity_or_404(db: Session, opportunity_id: int) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(404, "Opportunity not found")
    return opportunity


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard", response_model=DashboardOut, responses={500: {"model": ErrorResponse}})
def dashboard(db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date()
    open_status = ["OPEN", "IN_PROGRESS"]
    followups = list(db.scalars(select(ActionItem).where(ActionItem.status.in_(open_status), ActionItem.due_date == today).order_by(ActionItem.priority.desc())))
    overdue = list(db.scalars(select(ActionItem).where(ActionItem.status.in_(open_status), ActionItem.due_date < today).order_by(ActionItem.due_date)))
    opportunities = list(db.scalars(select(Opportunity).where(Opportunity.stage.not_in(["WON", "LOST"])).order_by(Opportunity.value.desc()).limit(6)))
    meetings = list(db.scalars(select(Meeting).options(selectinload(Meeting.insights), selectinload(Meeting.action_items)).order_by(Meeting.meeting_date.desc()).limit(5)))
    return DashboardOut(today_follow_ups=followups, overdue_actions=overdue, open_opportunities=opportunities, recent_meetings=meetings)


@app.get("/api/customers", response_model=list[CustomerListItem], responses={500: {"model": ErrorResponse}})
def list_customers(search: str | None = Query(default=None, max_length=100), db: Session = Depends(get_db)):
    stmt = select(Customer).order_by(Customer.name)
    if search:
        stmt = stmt.where(Customer.name.ilike(f"%{search.strip()}%"))
    return list(db.scalars(stmt))


@app.get("/api/customers/{customer_id}", response_model=CustomerOut, responses={404: {"model": ErrorResponse}})
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    return get_customer_or_404(db, customer_id, full=True)


@app.get("/api/customers/{customer_id}/history", response_model=CustomerHistory, responses={404: {"model": ErrorResponse}})
def customer_history(customer_id: int, db: Session = Depends(get_db)):
    customer = get_customer_or_404(db, customer_id, full=True)
    return CustomerHistory(customer=customer, meetings=sorted(customer.meetings, key=lambda m: m.meeting_date, reverse=True), opportunities=customer.opportunities, action_items=customer.action_items)


@app.get("/api/customers/{customer_id}/brief", response_model=CustomerBrief, responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}})
def customer_brief(customer_id: int, db: Session = Depends(get_db)):
    return brief_customer(db, customer_id)


@app.post("/api/ai/brief/{customer_id}", response_model=CustomerBrief, responses={404: {"model": ErrorResponse}})
def customer_brief_alias(customer_id: int, db: Session = Depends(get_db)):
    return brief_customer(db, customer_id)


@app.get("/api/meetings", response_model=list[MeetingOut])
def list_meetings(customer_id: int | None = None, limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    stmt = select(Meeting).options(selectinload(Meeting.insights), selectinload(Meeting.action_items)).order_by(Meeting.meeting_date.desc()).limit(limit)
    if customer_id:
        stmt = stmt.where(Meeting.customer_id == customer_id)
    return list(db.scalars(stmt))


@app.get("/api/meetings/{meeting_id:int}", response_model=MeetingOut, responses={404: {"model": ErrorResponse}})
def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    return get_meeting_or_404(db, meeting_id)


@app.post("/api/meetings", response_model=MeetingOut, status_code=201, responses={404: {"model": ErrorResponse}})
def create_manual_meeting(payload: MeetingCreate, db: Session = Depends(get_db)):
    get_customer_or_404(db, payload.customer_id)
    if payload.contact_id:
        contact = db.get(Contact, payload.contact_id)
        if not contact or contact.customer_id != payload.customer_id:
            raise HTTPException(422, "Contact does not belong to customer")
    meeting = Meeting(**payload.model_dump())
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return get_meeting_or_404(db, meeting.id)


@app.post("/api/meetings/analyze", response_model=MeetingAnalysisResponse, responses={502: {"model": ErrorResponse}})
@app.post("/api/ai/analyze-meeting", response_model=MeetingAnalysisResponse, responses={502: {"model": ErrorResponse}})
def analyze_meeting_endpoint(payload: MeetingAnalysisRequest, db: Session = Depends(get_db)):
    analysis, source = analyze_meeting(db, payload.transcript, payload.meeting_date or datetime.now(timezone.utc).date())
    return MeetingAnalysisResponse(analysis=analysis, match=match_customer(db, analysis.customer_name), source=source)


def save_confirmed_meeting(payload: MeetingConfirmRequest, db: Session) -> Meeting:
    customer = get_customer_or_404(db, payload.customer_id)
    if payload.contact_id:
        contact = db.get(Contact, payload.contact_id)
        if not contact or contact.customer_id != customer.id:
            raise HTTPException(422, "Contact does not belong to customer")
    meeting = Meeting(customer_id=customer.id, contact_id=payload.contact_id, meeting_date=payload.meeting_date, title=payload.title, transcript=payload.transcript, summary=payload.analysis.summary or "Meeting summary unavailable", sentiment=payload.analysis.sentiment)
    db.add(meeting)
    db.flush()
    insights = {
        "REQUIREMENT": payload.analysis.requirements,
        "PAIN_POINT": payload.analysis.pain_points,
        "CUSTOMER_CONCERN": payload.analysis.customer_concerns,
        "COMPETITOR": payload.analysis.competitors,
        "OPPORTUNITY": payload.analysis.opportunities,
    }
    for insight_type, values in insights.items():
        for value in values:
            db.add(MeetingInsight(meeting_id=meeting.id, type=insight_type, content=value))
    for item in payload.analysis.action_items:
        db.add(ActionItem(meeting_id=meeting.id, customer_id=customer.id, task=item.task, due_date=item.due_date, priority=item.priority, status="OPEN"))
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("confirm_meeting_db_error customer_id=%s", customer.id)
        raise HTTPException(503, "Unable to save the meeting right now") from exc
    return get_meeting_or_404(db, meeting.id)


@app.post("/api/meetings/confirm", response_model=MeetingOut, status_code=201, responses={404: {"model": ErrorResponse}})
def confirm_new_meeting(payload: MeetingConfirmRequest, db: Session = Depends(get_db)):
    return save_confirmed_meeting(payload, db)


@app.post("/api/meetings/{meeting_id:int}/confirm", response_model=MeetingOut, responses={404: {"model": ErrorResponse}})
def confirm_meeting_alias(meeting_id: int, payload: MeetingConfirmRequest, db: Session = Depends(get_db)):
    """Compatibility endpoint. A client-side draft uses its own id; no draft is persisted before confirmation."""
    if meeting_id != 0:
        get_meeting_or_404(db, meeting_id)
    return save_confirmed_meeting(payload, db)


@app.post("/api/transcription", response_model=TranscriptionResponse, responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def transcription(file: UploadFile = File(...)):
    allowed = {"audio/webm", "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/ogg", "audio/mpga", "audio/m4a"}
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in allowed:
        return error_response(400, "INVALID_AUDIO", "Upload a supported audio file.")
    content = await file.read(settings.max_audio_bytes + 1)
    if not content or len(content) > settings.max_audio_bytes:
        return error_response(413, "AUDIO_TOO_LARGE", "Audio must be smaller than 25 MB.")
    suffix = Path(file.filename or "recording.webm").suffix.casefold()
    if suffix not in {".webm", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".flac"}:
        return error_response(400, "INVALID_AUDIO", "Audio file extension is not supported.")
    return TranscriptionResponse(transcript=transcribe_audio(file.filename or "recording.webm", content_type, content), source="openai")


@app.post("/api/ai/ask", response_model=AskResponse, responses={502: {"model": ErrorResponse}})
def ask(payload: AskRequest, db: Session = Depends(get_db)):
    return ask_salespilot(db, payload.question)


@app.get("/api/action-items", response_model=list[ActionItemOut])
def list_action_items(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(ActionItem).order_by(ActionItem.due_date.nullslast(), ActionItem.priority.desc())
    if status:
        stmt = stmt.where(ActionItem.status == status)
    return list(db.scalars(stmt))


@app.get("/api/action-items/today", response_model=list[ActionItemOut])
def action_items_today(db: Session = Depends(get_db)):
    return list(db.scalars(select(ActionItem).where(ActionItem.status.in_(["OPEN", "IN_PROGRESS"]), ActionItem.due_date == datetime.now(timezone.utc).date()).order_by(ActionItem.priority.desc())))


@app.get("/api/action-items/overdue", response_model=list[ActionItemOut])
def action_items_overdue(db: Session = Depends(get_db)):
    return list(db.scalars(select(ActionItem).where(ActionItem.status.in_(["OPEN", "IN_PROGRESS"]), ActionItem.due_date < datetime.now(timezone.utc).date()).order_by(ActionItem.due_date)))


@app.post("/api/action-items", response_model=ActionItemOut, status_code=201, responses={404: {"model": ErrorResponse}})
def create_action_item(payload: ActionItemCreate, db: Session = Depends(get_db)):
    get_customer_or_404(db, payload.customer_id)
    if payload.meeting_id:
        meeting = get_meeting_or_404(db, payload.meeting_id)
        if meeting.customer_id != payload.customer_id:
            raise HTTPException(422, "Meeting does not belong to customer")
    action = ActionItem(**payload.model_dump(), status="OPEN")
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@app.patch("/api/action-items/{action_id}", response_model=ActionItemOut, responses={404: {"model": ErrorResponse}})
def update_action_item(action_id: int, payload: ActionItemPatch, db: Session = Depends(get_db)):
    action = get_action_or_404(db, action_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(action, field, value)
    db.commit()
    db.refresh(action)
    return action


@app.get("/api/opportunities", response_model=list[OpportunityOut])
def list_opportunities(customer_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Opportunity).order_by(Opportunity.value.desc())
    if customer_id:
        stmt = stmt.where(Opportunity.customer_id == customer_id)
    return list(db.scalars(stmt))


@app.get("/api/opportunities/{opportunity_id}", response_model=OpportunityOut, responses={404: {"model": ErrorResponse}})
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    return get_opportunity_or_404(db, opportunity_id)


@app.patch("/api/opportunities/{opportunity_id}", response_model=OpportunityOut, responses={404: {"model": ErrorResponse}})
def update_opportunity(opportunity_id: int, payload: OpportunityPatch, db: Session = Depends(get_db)):
    opportunity = get_opportunity_or_404(db, opportunity_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(opportunity, field, value)
    db.commit()
    db.refresh(opportunity)
    return opportunity
