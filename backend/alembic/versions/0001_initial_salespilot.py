python -m app.seed"""Initial SalesPilot CRM schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("email", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("customers", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("industry", sa.String(120), nullable=False), sa.Column("location", sa.String(160)), sa.Column("phone", sa.String(50)), sa.Column("email", sa.String(255)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_customers_name", "customers", ["name"], unique=True)
    op.create_table("contacts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(160), nullable=False), sa.Column("designation", sa.String(160)), sa.Column("email", sa.String(255)), sa.Column("phone", sa.String(50)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_contacts_customer_id", "contacts", ["customer_id"])
    op.create_index("ix_contacts_name", "contacts", ["name"])
    op.create_table("meetings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False), sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL")), sa.Column("meeting_date", sa.DateTime(timezone=True), nullable=False), sa.Column("title", sa.String(240), nullable=False), sa.Column("transcript", sa.Text()), sa.Column("summary", sa.Text(), nullable=False), sa.Column("sentiment", sa.String(30)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_meetings_customer_id", "meetings", ["customer_id"])
    op.create_index("ix_meetings_contact_id", "meetings", ["contact_id"])
    op.create_index("ix_meetings_meeting_date", "meetings", ["meeting_date"])
    op.create_table("meeting_insights", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False), sa.Column("type", sa.String(40), nullable=False), sa.Column("content", sa.Text(), nullable=False))
    op.create_index("ix_meeting_insights_meeting_id", "meeting_insights", ["meeting_id"])
    op.create_index("ix_meeting_insights_type", "meeting_insights", ["type"])
    op.create_table("action_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id", ondelete="SET NULL")), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False), sa.Column("task", sa.Text(), nullable=False), sa.Column("due_date", sa.Date()), sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"), sa.Column("priority", sa.String(20), nullable=False, server_default="MEDIUM"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_action_items_customer_id", "action_items", ["customer_id"])
    op.create_index("ix_action_items_meeting_id", "action_items", ["meeting_id"])
    op.create_index("ix_action_items_due_date", "action_items", ["due_date"])
    op.create_index("ix_action_items_status", "action_items", ["status"])
    op.create_table("opportunities", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(240), nullable=False), sa.Column("description", sa.Text()), sa.Column("value", sa.Numeric(14, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False, server_default="INR"), sa.Column("stage", sa.String(50), nullable=False, server_default="DISCOVERY"), sa.Column("probability", sa.Integer(), nullable=False, server_default="0"), sa.Column("expected_close_date", sa.Date()), sa.Column("competitor", sa.String(160)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_opportunities_customer_id", "opportunities", ["customer_id"])
    op.create_table("customer_activities", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False), sa.Column("activity_type", sa.String(60), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("activity_date", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_customer_activities_customer_id", "customer_activities", ["customer_id"])
    op.create_index("ix_customer_activities_activity_date", "customer_activities", ["activity_date"])
    op.create_table("payments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False), sa.Column("amount", sa.Numeric(14, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False, server_default="INR"), sa.Column("payment_date", sa.Date(), nullable=False), sa.Column("status", sa.String(40), nullable=False))
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("customer_activities")
    op.drop_table("opportunities")
    op.drop_table("action_items")
    op.drop_table("meeting_insights")
    op.drop_table("meetings")
    op.drop_table("contacts")
    op.drop_table("customers")
    op.drop_table("users")
