"""OpenAI boundary: structured analysis and strictly allow-listed CRM tool calls."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
import json
import logging
import re
from typing import Any
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from .config import get_settings
from .models import ActionItem, Contact, Customer, CustomerActivity, Meeting, MeetingInsight, Opportunity, Payment
from .schemas import (
    AskResponse, Candidate, Citation, Confidence, CustomerBrief, ExtractedActionItem,
    FollowUp, MatchResult, MeetingAnalysis,
)

logger = logging.getLogger(__name__)


class SalesPilotAIError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _customer_name(customer: Customer) -> dict[str, Any]:
    return {"id": customer.id, "name": customer.name}


def match_customer(db: Session, raw_name: str | None) -> MatchResult:
    """Resolve deterministic DB matches; a low-confidence name is never auto-linked."""
    if not raw_name or not raw_name.strip():
        return MatchResult(match_status="UNKNOWN", confidence=0)
    customers = list(db.scalars(select(Customer).order_by(Customer.name)))
    normalized = re.sub(r"[^a-z0-9]", "", raw_name.casefold())
    exact = next((customer for customer in customers if re.sub(r"[^a-z0-9]", "", customer.name.casefold()) == normalized), None)
    if exact:
        return MatchResult(match_status="MATCHED", customer=Candidate(**_customer_name(exact)), candidates=[Candidate(**_customer_name(exact))], confidence=1)
    scored = sorted(
        ((fuzz.token_set_ratio(raw_name.casefold(), c.name.casefold()) / 100, c) for c in customers),
        reverse=True,
        key=lambda pair: pair[0],
    )
    if not scored or scored[0][0] < 0.60:
        return MatchResult(match_status="UNKNOWN", confidence=max(scored[0][0] if scored else 0, 0))
    score, customer = scored[0]
    # A shortened prefix is never sufficient when several real account names begin with it.
    prefix_matches = [c for c in customers if re.sub(r"[^a-z0-9]", "", c.name.casefold()).startswith(normalized)]
    if len(prefix_matches) > 1:
        return MatchResult(match_status="AMBIGUOUS", candidates=[Candidate(**_customer_name(c)) for c in prefix_matches[:5]], confidence=round(score, 2))
    close = [c for s, c in scored if s >= 0.72 and (score - s) <= 0.10]
    candidates = [Candidate(**_customer_name(c)) for c in close[:5]]
    if score < 0.86 or len(close) > 1:
        return MatchResult(match_status="AMBIGUOUS", candidates=candidates, confidence=round(score, 2))
    return MatchResult(
        match_status="MATCHED",
        customer=Candidate(**_customer_name(customer)),
        candidates=candidates,
        confidence=round(score, 2),
    )


def _load_customer(db: Session, customer_id: int) -> Customer | None:
    return db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .options(
            selectinload(Customer.contacts), selectinload(Customer.meetings).selectinload(Meeting.insights),
            selectinload(Customer.opportunities), selectinload(Customer.action_items),
            selectinload(Customer.activities), selectinload(Customer.payments),
        )
    )


def _context_for_customer(customer: Customer) -> dict[str, Any]:
    return {
        "customer": {"name": customer.name, "industry": customer.industry, "location": customer.location},
        "contacts": [{"name": c.name, "role": c.designation} for c in customer.contacts],
        "meetings": [
            {"date": m.meeting_date.date().isoformat(), "summary": m.summary,
             "insights": [{"type": i.type, "content": i.content} for i in m.insights]}
            for m in sorted(customer.meetings, key=lambda x: x.meeting_date, reverse=True)[:5]
        ],
        "opportunities": [
            {"name": o.name, "value": str(o.value), "currency": o.currency, "stage": o.stage,
             "probability": o.probability, "competitor": o.competitor}
            for o in customer.opportunities
        ],
        "open_actions": [
            {"task": a.task, "due_date": a.due_date.isoformat() if a.due_date else None, "priority": a.priority}
            for a in customer.action_items if a.status in {"OPEN", "IN_PROGRESS"}
        ],
        "activity": [{"type": a.activity_type, "description": a.description, "date": a.activity_date.date().isoformat()}
                     for a in sorted(customer.activities, key=lambda x: x.activity_date, reverse=True)[:4]],
        "payments": [{"amount": str(p.amount), "currency": p.currency, "status": p.status,
                      "date": p.payment_date.isoformat()} for p in customer.payments[-3:]],
    }


def _database_brief(customer: Customer) -> CustomerBrief:
    context = _context_for_customer(customer)
    meetings = context["meetings"]
    insights = [insight for meeting in meetings for insight in meeting["insights"]]
    requirements = [i["content"] for i in insights if i["type"] == "REQUIREMENT"]
    pain_points = [i["content"] for i in insights if i["type"] in {"PAIN_POINT", "CUSTOMER_CONCERN"}]
    competitors = list({i["content"] for i in insights if i["type"] == "COMPETITOR"} | {o["competitor"] for o in context["opportunities"] if o["competitor"]})
    open_ops = [f"{o['name']}: {o['currency']} {o['value']} ({o['stage']}, {o['probability']}%)" for o in context["opportunities"]]
    actions = [f"{a['task']}" + (f" — due {a['due_date']}" if a["due_date"] else "") for a in context["open_actions"]]
    risks = []
    if pain_points:
        risks.append("Customer concerns recorded in prior meetings need a direct response.")
    if actions:
        risks.append("Open commitments should be addressed before introducing new asks.")
    if any(o["probability"] < 50 for o in context["opportunities"]):
        risks.append("At least one open opportunity has a probability below 50%.")
    latest_discussions = [m["summary"] for m in meetings[:3]]
    payment_text = "No recent payment activity is available."
    if context["payments"]:
        latest = context["payments"][-1]
        payment_text = f"Latest payment: {latest['currency']} {latest['amount']} on {latest['date']} ({latest['status']})."
    talking = ([f"Address: {pain_points[0]}"] if pain_points else []) + ([f"Confirm progress on: {actions[0]}"] if actions else [])
    if not talking:
        talking = ["Confirm priorities, decision process, and a measurable next step."]
    return CustomerBrief(
        customer_overview=f"{customer.name} is a {customer.industry} organization" + (f" in {customer.location}." if customer.location else "."),
        relationship_summary=f"{len(meetings)} recorded meeting(s), {len(context['opportunities'])} open opportunity record(s), and {len(actions)} open action item(s).",
        recent_discussions=latest_discussions,
        open_opportunities=open_ops,
        requirements=requirements,
        pain_points=pain_points,
        competitors=competitors,
        outstanding_actions=actions,
        payment_activity_summary=payment_text,
        risks=risks,
        recommended_talking_points=talking,
        recommended_questions=[
            "Has anything changed in your delivery, pricing, or evaluation criteria?",
            "Who else needs to be involved before the next decision?",
            "What would make the next step successful for your team?",
        ],
        source="local_demo",
    )


def local_analyze(transcript: str, meeting_date: date) -> MeetingAnalysis:
    """Conservative offline draft. It only preserves explicit words from the transcript."""
    customer = None
    for pattern in (r"(?:from|at|with)\s+([A-Z][\w& .-]{2,60}?)(?:\s+(?:today|yesterday|about|regarding|who|and|,|\.))",):
        found = re.search(pattern, transcript)
        if found:
            customer = found.group(1).strip()
            break
    contact = None
    found_contact = re.search(r"(?:met|spoke (?:to|with)|with)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", transcript)
    if found_contact:
        contact = found_contact.group(1)
    lowered = transcript.casefold()
    competitors = []
    comp = re.search(r"([A-Z][A-Za-z0-9& -]{1,40})\s+(?:is|are|was|were)?\s*offering|(?:competitor|competition)\s+(?:is|was)?\s*([A-Z][A-Za-z0-9& -]{1,40})", transcript)
    if comp:
        competitors.append(next(part.strip() for part in comp.groups() if part))
    requirements = []
    req = re.search(r"(?:requirement|need|needs|require)\s+(?:of|for|around|approximately)?\s*([^.!]{3,160})", transcript, re.I)
    if req:
        requirements.append(req.group(1).strip())
    concerns = [word for word in ("price", "delivery", "reliability", "quality", "timeline") if word in lowered]
    action_items: list[ExtractedActionItem] = []
    for match in re.finditer(r"(?:send|share|follow up|call|prepare)\s+([^.!]{3,180})", transcript, re.I):
        task = match.group(0).strip()
        action_items.append(ExtractedActionItem(task=task[:300], priority="HIGH" if "quotation" in task.casefold() else "MEDIUM"))
    # Never guess relative dates offline: retain null and demand review.
    return MeetingAnalysis(
        customer_name=customer,
        contact_name=contact,
        meeting_date=meeting_date,
        summary=transcript.strip()[:800],
        requirements=requirements,
        pain_points=concerns,
        customer_concerns=concerns,
        competitors=competitors,
        opportunities=[],
        sentiment="MIXED" if concerns else "NEUTRAL",
        action_items=action_items[:8],
        follow_up=FollowUp(required=bool(action_items), date=None, clarification_needed="next " in lowered or "friday" in lowered),
        confidence=Confidence(customer=0.50 if customer else 0, contact=0.50 if contact else 0, overall=0.45),
    )


def _meeting_schema() -> dict[str, Any]:
    schema = MeetingAnalysis.model_json_schema()
    # Responses structured output accepts JSON schema. Pydantic supplies all required fields and validation.
    return schema


class SalesToolService:
    """Controlled read-only tool implementations exposed to the ask agent."""
    def __init__(self, db: Session):
        self.db = db

    def find_customer(self, name: str) -> dict[str, Any]:
        match = match_customer(self.db, name)
        return match.model_dump(mode="json")

    def get_customer_profile(self, customer_id: int) -> dict[str, Any]:
        customer = _load_customer(self.db, customer_id)
        if not customer:
            return {"error": "Customer not found"}
        return _context_for_customer(customer)

    def get_customer_history(self, customer_id: int, limit: int = 5) -> dict[str, Any]:
        customer = _load_customer(self.db, customer_id)
        if not customer:
            return {"error": "Customer not found"}
        context = _context_for_customer(customer)
        context["meetings"] = context["meetings"][:limit]
        return context

    def get_recent_meetings(self, customer_id: int | None = None, limit: int = 5) -> list[dict[str, Any]]:
        stmt = select(Meeting).options(selectinload(Meeting.customer)).order_by(Meeting.meeting_date.desc()).limit(limit)
        if customer_id:
            stmt = stmt.where(Meeting.customer_id == customer_id)
        return [{"id": m.id, "customer_id": m.customer_id, "customer": m.customer.name, "date": m.meeting_date.isoformat(), "summary": m.summary} for m in self.db.scalars(stmt)]

    def get_open_opportunities(self, customer_id: int | None = None) -> list[dict[str, Any]]:
        stmt = select(Opportunity).options(selectinload(Opportunity.customer)).where(Opportunity.stage.not_in(["WON", "LOST"]))
        if customer_id:
            stmt = stmt.where(Opportunity.customer_id == customer_id)
        return [{"id": o.id, "customer_id": o.customer_id, "customer": o.customer.name, "name": o.name,
                 "value": str(o.value), "currency": o.currency, "stage": o.stage, "probability": o.probability,
                 "competitor": o.competitor} for o in self.db.scalars(stmt)]

    def get_customer_action_items(self, customer_id: int | None = None, status: str = "OPEN") -> list[dict[str, Any]]:
        stmt = select(ActionItem).options(selectinload(ActionItem.customer)).where(ActionItem.status == status)
        if customer_id:
            stmt = stmt.where(ActionItem.customer_id == customer_id)
        return [{"id": a.id, "customer_id": a.customer_id, "customer": a.customer.name, "task": a.task,
                 "due_date": a.due_date.isoformat() if a.due_date else None, "priority": a.priority} for a in self.db.scalars(stmt)]

    def get_customer_activity(self, customer_id: int, limit: int = 5) -> list[dict[str, Any]]:
        stmt = select(CustomerActivity).where(CustomerActivity.customer_id == customer_id).order_by(CustomerActivity.activity_date.desc()).limit(limit)
        return [{"id": a.id, "activity_type": a.activity_type, "description": a.description, "date": a.activity_date.isoformat()} for a in self.db.scalars(stmt)]


READ_TOOLS = [
    {"type": "function", "name": "find_customer", "description": "Find CRM customers by name. Use before customer-specific questions.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "get_customer_profile", "description": "Get a single customer's CRM profile and related factual context.", "parameters": {"type": "object", "properties": {"customer_id": {"type": "integer"}}, "required": ["customer_id"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "get_customer_history", "description": "Get a customer's recent meeting history and related CRM context.", "parameters": {"type": "object", "properties": {"customer_id": {"type": "integer"}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["customer_id", "limit"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "get_recent_meetings", "description": "Get most recent recorded meetings, optionally for one customer.", "parameters": {"type": "object", "properties": {"customer_id": {"type": ["integer", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["customer_id", "limit"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "get_open_opportunities", "description": "Get open CRM opportunities, optionally for one customer.", "parameters": {"type": "object", "properties": {"customer_id": {"type": ["integer", "null"]}}, "required": ["customer_id"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "get_customer_action_items", "description": "Get open CRM action items, optionally for one customer.", "parameters": {"type": "object", "properties": {"customer_id": {"type": ["integer", "null"]}, "status": {"type": "string", "enum": ["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"]}}, "required": ["customer_id", "status"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "get_customer_activity", "description": "Get recorded customer activity. Requires a customer ID.", "parameters": {"type": "object", "properties": {"customer_id": {"type": "integer"}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["customer_id", "limit"], "additionalProperties": False}, "strict": True},
]


WRITE_TOOL_CATALOG = [
    {"name": "create_meeting", "description": "Create a confirmed meeting. Not available to conversational AI; HTTP confirmation requires a user review."},
    {"name": "create_action_item", "description": "Create a confirmed action item. Not available to conversational AI."},
    {"name": "update_opportunity", "description": "Update a confirmed opportunity. Not available to conversational AI."},
    {"name": "create_follow_up", "description": "Create a confirmed follow-up. Not available to conversational AI."},
]


def _call_read_tool(service: SalesToolService, name: str, arguments: dict[str, Any]) -> Any:
    allowed = {"find_customer", "get_customer_profile", "get_customer_history", "get_recent_meetings", "get_open_opportunities", "get_customer_action_items", "get_customer_activity"}
    if name not in allowed:
        return {"error": "Tool is not allowed"}
    try:
        return getattr(service, name)(**arguments)
    except (TypeError, ValueError) as exc:
        return {"error": f"Invalid tool arguments: {exc}"}


def _openai_client():
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=settings.openai_api_key, timeout=25.0, max_retries=1)


def analyze_meeting(db: Session, transcript: str, meeting_date: date) -> tuple[MeetingAnalysis, str]:
    client = _openai_client()
    if not client:
        return local_analyze(transcript, meeting_date), "local_demo"
    try:
        response = client.responses.create(
            model=get_settings().openai_model,
            instructions=("Extract only information explicitly stated in the sales meeting transcript. Never infer missing facts. "
                          f"The meeting date is {meeting_date.isoformat()}; resolve relative dates only when unambiguous. "
                          "Use null when unknown. Return the required JSON schema."),
            input=transcript,
            text={"format": {"type": "json_schema", "name": "meeting_analysis", "schema": _meeting_schema(), "strict": True}},
        )
        return MeetingAnalysis.model_validate_json(response.output_text), "openai"
    except Exception as exc:  # SDK exception hierarchy can change; do not leak particulars.
        logger.warning("meeting_analysis_failed error_type=%s", type(exc).__name__)
        raise SalesPilotAIError("AI_ANALYSIS_FAILED", "Unable to analyze this meeting right now.") from exc


def brief_customer(db: Session, customer_id: int) -> CustomerBrief:
    customer = _load_customer(db, customer_id)
    if not customer:
        raise SalesPilotAIError("CUSTOMER_NOT_FOUND", "Customer not found.")
    fallback = _database_brief(customer)
    client = _openai_client()
    if not client:
        return fallback
    try:
        response = client.responses.create(
            model=get_settings().openai_model,
            instructions=("Create a concise sales meeting brief strictly from supplied CRM facts. "
                          "Do not invent information. If there are no facts for a category, return an empty list or say unavailable."),
            input=json.dumps(_context_for_customer(customer)),
            text={"format": {"type": "json_schema", "name": "customer_brief", "schema": CustomerBrief.model_json_schema(), "strict": True}},
        )
        brief = CustomerBrief.model_validate_json(response.output_text)
        return brief.model_copy(update={"source": "openai"})
    except Exception as exc:
        logger.warning("customer_brief_failed customer_id=%s error_type=%s", customer_id, type(exc).__name__)
        return fallback


def _citations_from_tools(outputs: list[Any]) -> list[Citation]:
    citations: list[Citation] = []
    for output in outputs:
        records = output if isinstance(output, list) else []
        for record in records:
            if not isinstance(record, dict):
                continue
            customer = record.get("customer")
            if customer:
                record_type = "OPPORTUNITY" if "value" in record else "ACTION_ITEM" if "task" in record else "MEETING"
                citations.append(Citation(customer_id=record.get("customer_id"), customer_name=customer, record_type=record_type, record_id=record.get("id"), detail=record.get("task") or record.get("name") or record.get("summary", "CRM record")))
    return citations[:12]


def ask_salespilot(db: Session, question: str) -> AskResponse:
    client = _openai_client()
    service = SalesToolService(db)
    if not client:
        return local_ask(db, question)
    try:
        instructions = ("You are SalesPilot. Answer only with information returned by the CRM tools. "
                        "Never invent customer facts, figures, dates, or status. If a tool does not contain the answer, say it is unavailable. "
                        "Use the smallest set of read-only tools needed. Do not claim a record is overdue unless its due date is before today.")
        initial_input: list[Any] = [{"role": "user", "content": question}]
        response = client.responses.create(model=get_settings().openai_model, instructions=instructions, input=initial_input, tools=READ_TOOLS)
        tool_outputs: list[Any] = []
        for _ in range(4):
            calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
            if not calls:
                break
            next_input: list[Any] = list(response.output)
            for call in calls:
                arguments = json.loads(call.arguments)
                output = _call_read_tool(service, call.name, arguments)
                tool_outputs.append(output)
                next_input.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(output, default=str)})
            response = client.responses.create(model=get_settings().openai_model, instructions=instructions, input=next_input, tools=READ_TOOLS)
        return AskResponse(answer=response.output_text or "That information is unavailable in the CRM.", citations=_citations_from_tools(tool_outputs), source="openai_tools")
    except Exception as exc:
        logger.warning("ask_salespilot_failed error_type=%s", type(exc).__name__)
        raise SalesPilotAIError("AI_QUERY_FAILED", "SalesPilot could not answer that question right now.") from exc


def local_ask(db: Session, question: str) -> AskResponse:
    """Database-only query fallback, intentionally narrow rather than pretending to understand every question."""
    lowered = question.casefold()
    today = _today()
    if any(term in lowered for term in ("overdue", "follow up", "follow-up", "followup", "today")):
        overdue = list(db.scalars(select(ActionItem).options(selectinload(ActionItem.customer)).where(ActionItem.status.in_(["OPEN", "IN_PROGRESS"]), ActionItem.due_date < today).order_by(ActionItem.due_date)))
        today_items = list(db.scalars(select(ActionItem).options(selectinload(ActionItem.customer)).where(ActionItem.status.in_(["OPEN", "IN_PROGRESS"]), ActionItem.due_date == today).order_by(ActionItem.priority.desc())))
        items = overdue if "overdue" in lowered else today_items
        label = "overdue" if "overdue" in lowered else "due today"
        if not items:
            return AskResponse(answer=f"No open follow-ups are {label} in the CRM.", source="local_database")
        lines = [f"{len(items)} open follow-up(s) are {label}:"]
        citations = []
        for item in items:
            lines.append(f"• {item.customer.name}: {item.task}" + (f" (due {item.due_date})" if item.due_date else ""))
            citations.append(Citation(customer_id=item.customer_id, customer_name=item.customer.name, record_type="ACTION_ITEM", record_id=item.id, detail=item.task))
        return AskResponse(answer="\n".join(lines), citations=citations, source="local_database")
    if any(term in lowered for term in ("highest", "largest", "opportunity", "risk")):
        ops = list(db.scalars(select(Opportunity).options(selectinload(Opportunity.customer)).where(Opportunity.stage.not_in(["WON", "LOST"])).order_by(Opportunity.value.desc())))
        if not ops:
            return AskResponse(answer="No open opportunities are available in the CRM.", source="local_database")
        if "risk" in lowered:
            ops = [o for o in ops if o.probability < 50]
        if not ops:
            return AskResponse(answer="No at-risk opportunities are available in the CRM using the probability below 50% rule.", source="local_database")
        lines = ["Open opportunities from the CRM:"]
        citations = []
        for op in ops[:5]:
            lines.append(f"• {op.customer.name}: {op.currency} {op.value} — {op.stage}, {op.probability}% probability.")
            citations.append(Citation(customer_id=op.customer_id, customer_name=op.customer.name, record_type="OPPORTUNITY", record_id=op.id, detail=op.name))
        return AskResponse(answer="\n".join(lines), citations=citations, source="local_database")
    matched = match_customer(db, question)
    if matched.match_status == "MATCHED" and matched.customer:
        customer = _load_customer(db, matched.customer.id)
        if customer:
            recent = sorted(customer.meetings, key=lambda m: m.meeting_date, reverse=True)[:3]
            if not recent:
                return AskResponse(answer=f"{customer.name} has no recorded meetings in the CRM.", source="local_database")
            return AskResponse(answer="\n".join([f"Recent meetings with {customer.name}:"] + [f"• {m.meeting_date.date()}: {m.summary}" for m in recent]), citations=[Citation(customer_id=customer.id, customer_name=customer.name, record_type="MEETING", record_id=m.id, detail=m.summary) for m in recent], source="local_database")
    return AskResponse(answer="That information is unavailable in the CRM. Try asking about follow-ups, opportunities, or a customer by name.", source="local_database")


def transcribe_audio(filename: str, mime_type: str, content: bytes) -> str:
    client = _openai_client()
    if not client:
        raise SalesPilotAIError("OPENAI_NOT_CONFIGURED", "Audio transcription needs a backend OPENAI_API_KEY.")
    try:
        response = client.audio.transcriptions.create(
            model=get_settings().openai_transcription_model,
            file=(filename, content, mime_type),
        )
        return response.text
    except Exception as exc:
        logger.warning("transcription_failed error_type=%s", type(exc).__name__)
        raise SalesPilotAIError("TRANSCRIPTION_FAILED", "Unable to transcribe the recording.") from exc
