from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app.models import Customer, Contact, Meeting, MeetingInsight, Opportunity, ActionItem
from datetime import datetime, timedelta, timezone
from decimal import Decimal


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    customer = Customer(name="ABC Pharma", industry="Pharmaceuticals", location="Mumbai", email="abc@example.test", phone="+91 000")
    nearby = Customer(name="ABC Pharmaceuticals", industry="Pharmaceuticals", location="Delhi", email="abcp@example.test", phone="+91 001")
    session.add_all([customer, nearby]); session.flush()
    contact = Contact(customer_id=customer.id, name="Rahul Sharma", designation="Procurement Manager", email="rahul@example.test", phone="+91 000")
    session.add(contact); session.flush()
    meeting = Meeting(customer_id=customer.id, contact_id=contact.id, meeting_date=datetime.now(timezone.utc) - timedelta(days=3), title="Review", summary="Discussed delivery reliability and quotation.", sentiment="MIXED")
    session.add(meeting); session.flush()
    session.add_all([MeetingInsight(meeting_id=meeting.id, type="PAIN_POINT", content="Delivery reliability"), MeetingInsight(meeting_id=meeting.id, type="COMPETITOR", content="MediSource")])
    session.add_all([Opportunity(customer_id=customer.id, name="Supply expansion", value=Decimal("3200000"), currency="INR", stage="NEGOTIATION", probability=60, competitor="MediSource"), ActionItem(customer_id=customer.id, meeting_id=meeting.id, task="Send quotation", due_date=(datetime.now(timezone.utc) - timedelta(days=1)).date(), status="OPEN", priority="HIGH")])
    session.commit()
    try:
        yield session
    finally:
        session.close(); Base.metadata.drop_all(engine); engine.dispose()


@pytest.fixture()
def client(db: Session) -> Generator[TestClient, None, None]:
    def override() -> Generator[Session, None, None]:
        yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
