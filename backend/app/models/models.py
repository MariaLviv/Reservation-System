from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Date, Time, Enum, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class AppointmentStatus(str, enum.Enum):
    BOOKED = "booked"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    name = Column(String(255), nullable=False)
    birthdate = Column(Date, nullable=False)
    is_blacklisted = Column(Boolean, default=False, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)
    calendar_feed_token = Column(String(255), unique=True, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    appointments = relationship("Appointment", back_populates="user")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.BOOKED, nullable=False)
    notes = Column(Text, nullable=True)
    cancelled_by = Column(String(10), nullable=True)  # 'user' or 'admin'
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="appointments")


class ScheduleConfig(Base):
    __tablename__ = "schedule_config"

    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    slot_duration = Column(Integer, nullable=False)  # in minutes
    working_days = Column(JSON, nullable=True)  # [0,1,2,3,4] for Mon-Fri, 0=Monday, 6=Sunday


class DayOff(Base):
    __tablename__ = "days_off"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True, index=True)


class BlockedSlot(Base):
    __tablename__ = "blocked_slots"

    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified = Column(Boolean, default=False, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_phone = Column(String(20), nullable=False, index=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class TelegramNotification(Base):
    __tablename__ = "telegram_notifications"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), nullable=False, index=True)
    notification_type = Column(String(50), nullable=False)  # 'cancellation', 'reminder', etc.
    message_data = Column(JSON, nullable=False)  # Contains appointment details, etc.
    sent = Column(Boolean, default=False, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

