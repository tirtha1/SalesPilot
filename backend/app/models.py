from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Customer(Base, Timestamped):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(120))
    location: Mapped[Optional[str]] = mapped_column(String(160))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    contacts: Mapped[list[Contact]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    meetings: Mapped[list[Meeting]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    opportunities: Mapped[list[Opportunity]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    action_items: Mapped[list[ActionItem]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    activities: Mapped[list[CustomerActivity]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    designation: Mapped[Optional[str]] = mapped_column(String(160))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    customer: Mapped[Customer] = relationship(back_populates="contacts")
    meetings: Mapped[list[Meeting]] = relationship(back_populates="contact")


class Meeting(Base, Timestamped):
    __tablename__ = "meetings"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    meeting_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(String(240))
    transcript: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[Optional[str]] = mapped_column(String(30))
    customer: Mapped[Customer] = relationship(back_populates="meetings")
    contact: Mapped[Optional[Contact]] = relationship(back_populates="meetings")
    insights: Mapped[list[MeetingInsight]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    action_items: Mapped[list[ActionItem]] = relationship(back_populates="meeting", cascade="all, delete-orphan")


class MeetingInsight(Base):
    __tablename__ = "meeting_insights"
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    content: Mapped[str] = mapped_column(Text)
    meeting: Mapped[Meeting] = relationship(back_populates="insights")


class ActionItem(Base, Timestamped):
    __tablename__ = "action_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[Optional[int]] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    task: Mapped[str] = mapped_column(Text)
    due_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(30), default="OPEN", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    meeting: Mapped[Optional[Meeting]] = relationship(back_populates="action_items")
    customer: Mapped[Customer] = relationship(back_populates="action_items")


class Opportunity(Base, Timestamped):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[Optional[str]] = mapped_column(Text)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    stage: Mapped[str] = mapped_column(String(50), default="DISCOVERY")
    probability: Mapped[int] = mapped_column(Integer, default=0)
    expected_close_date: Mapped[Optional[date]] = mapped_column(Date)
    competitor: Mapped[Optional[str]] = mapped_column(String(160))
    customer: Mapped[Customer] = relationship(back_populates="opportunities")


class CustomerActivity(Base):
    __tablename__ = "customer_activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text)
    activity_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    customer: Mapped[Customer] = relationship(back_populates="activities")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    payment_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40))
    customer: Mapped[Customer] = relationship(back_populates="payments")
