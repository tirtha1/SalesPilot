"""Idempotent fictional demo data for a convincing local SalesPilot walkthrough."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select
from .database import SessionLocal
from .models import ActionItem, Contact, Customer, CustomerActivity, Meeting, MeetingInsight, Opportunity, Payment, User


def seed() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(Customer.id).limit(1)):
            print("Seed skipped: customers already exist.")
            return
        today = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
        db.add(User(name="Tirtha Mehta", email="tirtha.mehta@example.test"))
        definitions = [
            {"name": "ABC Pharma", "industry": "Pharmaceuticals", "location": "Mumbai", "email": "procurement@abcpharma.example", "phone": "+91 22 5550 0101", "contact": ("Rahul Sharma", "Procurement Manager"), "op": ("Supply expansion", "500 units/month supply proposal", "3200000", "NEGOTIATION", 68, "MediSource"), "summary": "Discussed 500 units per month. Rahul requested a revised quotation and stressed delivery reliability.", "requirement": "Approximately 500 units per month", "pain": "Current supplier delivery is unreliable", "competitor": "MediSource is offering a lower price", "action": ("Send revised quotation to Rahul", -1, "HIGH"), "payment": ("845000", "PAID", -18)},
            {"name": "XYZ Healthcare", "industry": "Hospital Network", "location": "Bengaluru", "email": "sourcing@xyzhealthcare.example", "phone": "+91 80 5550 0202", "contact": ("Nisha Iyer", "Head of Strategic Sourcing"), "op": ("Critical-care equipment renewal", "Annual equipment renewal", "1800000", "PROPOSAL", 52, "Careline Systems"), "summary": "Nisha asked for clinical references and needs a response after sharing the proposal internally.", "requirement": "Clinical references and service-level documentation", "pain": "Service response-time visibility", "competitor": "Careline Systems is incumbent", "action": ("Call Nisha to review proposal feedback", 0, "HIGH"), "payment": ("510000", "PAID", -35)},
            {"name": "MediCorp", "industry": "Medical Devices", "location": "Pune", "email": "operations@medicorp.example", "phone": "+91 20 5550 0303", "contact": ("Dev Malhotra", "Operations Director"), "op": ("Regional rollout", "Phased rollout across west region", "1200000", "DISCOVERY", 36, "HealthSupply"), "summary": "Dev requested product information and a phased implementation outline before involving finance.", "requirement": "Phased rollout plan with product specifications", "pain": "Limited warehouse capacity", "competitor": "HealthSupply has a local warehouse", "action": ("Share product information pack", 2, "MEDIUM"), "payment": ("210000", "PENDING", -4)},
            {"name": "HealthFirst Clinics", "industry": "Primary Care", "location": "Delhi", "email": "admin@healthfirst.example", "phone": "+91 11 5550 0404", "contact": ("Kavita Menon", "Clinic Operations Lead"), "op": ("Clinic automation pilot", "Pilot for 12 clinics", "950000", "QUALIFICATION", 42, "NexusCare"), "summary": "Kavita is interested in a pilot but needs training details and a clear rollout timeline.", "requirement": "Training plan for clinic staff", "pain": "Staff adoption risk", "competitor": "NexusCare has a shorter pilot offer", "action": ("Send training and rollout plan", 4, "MEDIUM"), "payment": ("150000", "PAID", -50)},
            {"name": "Apollo Distributors", "industry": "Healthcare Distribution", "location": "Chennai", "email": "commercial@apollodistributors.example", "phone": "+91 44 5550 0505", "contact": ("Arjun Rao", "Commercial Manager"), "op": ("Distribution partnership", "South India distribution agreement", "2450000", "NEGOTIATION", 74, "RapidMed"), "summary": "Arjun requested margin scenarios and wants confirmation of regional exclusivity terms.", "requirement": "Regional margin and exclusivity proposal", "pain": "Forecast accuracy", "competitor": "RapidMed has proposed an aggressive margin", "action": ("Prepare regional margin scenarios", -3, "HIGH"), "payment": ("650000", "PAID", -12)},
        ]
        for index, item in enumerate(definitions):
            customer = Customer(name=item["name"], industry=item["industry"], location=item["location"], email=item["email"], phone=item["phone"])
            db.add(customer)
            db.flush()
            contact = Contact(customer_id=customer.id, name=item["contact"][0], designation=item["contact"][1], email=f"{item['contact'][0].lower().replace(' ', '.')}@example.test", phone=item["phone"])
            db.add(contact)
            db.flush()
            op_name, description, value, stage, probability, competitor = item["op"]
            db.add(Opportunity(customer_id=customer.id, name=op_name, description=description, value=Decimal(value), currency="INR", stage=stage, probability=probability, expected_close_date=(today + timedelta(days=30 + index * 8)).date(), competitor=competitor))
            meeting = Meeting(customer_id=customer.id, contact_id=contact.id, meeting_date=today - timedelta(days=4 + index * 3), title="Account review", transcript=None, summary=item["summary"], sentiment="MIXED")
            db.add(meeting)
            db.flush()
            for kind, content in (("REQUIREMENT", item["requirement"]), ("PAIN_POINT", item["pain"]), ("COMPETITOR", item["competitor"])):
                db.add(MeetingInsight(meeting_id=meeting.id, type=kind, content=content))
            task, offset, priority = item["action"]
            db.add(ActionItem(meeting_id=meeting.id, customer_id=customer.id, task=task, due_date=(today + timedelta(days=offset)).date(), status="OPEN", priority=priority))
            amount, payment_status, payment_offset = item["payment"]
            db.add(Payment(customer_id=customer.id, amount=Decimal(amount), currency="INR", payment_date=(today + timedelta(days=payment_offset)).date(), status=payment_status))
            db.add(CustomerActivity(customer_id=customer.id, activity_type="EMAIL", description=f"Account update sent to {contact.name}.", activity_date=today - timedelta(days=2 + index)))
        db.commit()
        print("Seeded 5 fictional customers.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
