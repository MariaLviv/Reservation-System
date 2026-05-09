from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, date
from typing import List, Optional
from html import escape
from app.core.database import get_db
from app.models.schemas import (
    SendOTPRequest, VerifyOTPRequest, SessionResponse, AdminLoginRequest,
    ScheduleConfigCreate, ScheduleConfigResponse,
    DayOffCreate, DayOffResponse,
    BlockedSlotCreate, BlockedSlotResponse,
    AdminAppointmentCreate, AppointmentResponse, AppointmentUpdateRequest,
    UserNoteRequest, BlacklistRequest, UserResponse,
    DashboardStats, AuditLogResponse
)
from app.models.models import (
    User, Appointment, AppointmentStatus, ScheduleConfig, DayOff, BlockedSlot, OTPCode, AuditLog
)
from app.services.otp_service import otp_service
from app.services.audit_log_service import audit_log_service
from app.services.slot_service import slot_service
from app.core.cache import invalidate_slots_cache
from app.core.monitoring import track_appointment_created, track_user_registered
from app.core.websocket import manager
from app.core.config import settings
from app.utils.report_generator import ReportGenerator
from jose import jwt
from datetime import datetime, timedelta
import bcrypt

router = APIRouter(prefix="/admin", tags=["admin"])

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
MISSING_BIRTHDATE = date(1900, 1, 1)


def format_report_birthdate_and_age(user: User):
    if not user.birthdate or user.birthdate == MISSING_BIRTHDATE:
        return "", ""

    age = (datetime.now().date() - user.birthdate).days // 365
    return user.birthdate.strftime('%d.%m.%Y'), f"{age} років"


@router.post("/login", response_model=SessionResponse)
def admin_login(request: AdminLoginRequest, req: Request, db: Session = Depends(get_db)):
    """Admin login with username and password"""

    # Verify username
    if request.username != settings.ADMIN_USERNAME:
        raise HTTPException(status_code=401, detail="Невірний логін або пароль")

    # Verify password
    try:
        password_bytes = request.password.encode('utf-8')
        hash_bytes = settings.ADMIN_PASSWORD_HASH.encode('utf-8')
        if not bcrypt.checkpw(password_bytes, hash_bytes):
            raise HTTPException(status_code=401, detail="Невірний логін або пароль")
    except Exception as e:
        print(f"Password verification error: {e}")
        raise HTTPException(status_code=401, detail="Невірний логін або пароль")

    # Create session token
    token = create_session_token(request.username)

    # Log admin login
    audit_log_service.log_admin_login(
        db=db,
        admin_phone=request.username,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )

    return SessionResponse(
        message="Успішний вхід",
        session_token=token
    )


@router.get("/phone")
def get_admin_phone():
    """Get admin phone number for login form"""
    return {"phone": settings.ADMIN_PHONE}


def create_session_token(username: str) -> str:
    """Create session token for admin"""
    expires = datetime.utcnow() + timedelta(hours=settings.SESSION_EXPIRY_HOURS)
    payload = {
        "username": username,
        "exp": expires
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_admin_session(authorization: str = Header(None)) -> str:
    """Verify admin session token"""

    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("username")

            if username != settings.ADMIN_USERNAME:
                raise HTTPException(status_code=403, detail="Немає доступу")

            return username
        except Exception:
            raise HTTPException(status_code=401, detail="Невірна сесія")

    raise HTTPException(status_code=401, detail="Не авторизовано")


@router.post("/send-otp", response_model=SessionResponse)
def send_admin_otp(request: SendOTPRequest, db: Session = Depends(get_db)):
    """Send OTP to admin phone"""

    if request.phone != settings.ADMIN_PHONE:
        raise HTTPException(status_code=403, detail="Немає доступу")

    # Skip OTP in development mode
    if settings.SKIP_OTP_VERIFICATION:
        return SessionResponse(message="OTP пропущено (режим розробки)")

    success = otp_service.send_otp(db, request.phone)

    if not success:
        raise HTTPException(status_code=500, detail="Не вдалося надіслати код")

    return SessionResponse(message="Код надіслано")


@router.post("/verify-otp", response_model=SessionResponse)
def verify_admin_otp(request: VerifyOTPRequest, req: Request, db: Session = Depends(get_db)):
    """Verify admin OTP and create session"""

    if request.phone != settings.ADMIN_PHONE:
        raise HTTPException(status_code=403, detail="Немає доступу")

    # Skip OTP verification in development mode - accept any code
    if settings.SKIP_OTP_VERIFICATION:
        token = create_session_token(request.phone)

        # Log admin login
        audit_log_service.log_admin_login(
            db=db,
            admin_phone=request.phone,
            ip_address=req.client.host if req.client else None,
            user_agent=req.headers.get("user-agent")
        )

        return SessionResponse(
            message="Вхід виконано (режим розробки)",
            session_token=token
        )

    success = otp_service.verify_otp(db, request.phone, request.code)

    if not success:
        raise HTTPException(status_code=400, detail="Невірний або прострочений код")

    token = create_session_token(request.phone)

    # Log admin login
    audit_log_service.log_admin_login(
        db=db,
        admin_phone=request.phone,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )

    return SessionResponse(
        message="Авторизовано",
        session_token=token
    )


@router.post("/logout", response_model=SessionResponse)
def admin_logout(phone: str = Depends(verify_admin_session)):
    """Logout admin (client should delete token)"""
    return SessionResponse(message="Вихід виконано")


@router.get("/appointments", response_model=dict)
def get_all_appointments(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Get all appointments with optional filters and pagination"""

    query = db.query(Appointment)

    # Date filters
    if from_date:
        query = query.filter(Appointment.start_time >= datetime.combine(from_date, datetime.min.time()))

    if to_date:
        query = query.filter(Appointment.start_time <= datetime.combine(to_date, datetime.max.time()))

    # Status filter
    if status:
        query = query.filter(Appointment.status == status)

    # Search by user name or phone
    if search:
        search_pattern = f"%{search}%"
        query = query.join(User).filter(
            (User.name.ilike(search_pattern)) |
            (User.phone.like(search_pattern))
        )

    # Get total count
    total = query.count()

    # Apply pagination
    appointments = query.order_by(Appointment.start_time.desc()).offset(skip).limit(limit).all()

    # Convert to response models
    items = []
    for appointment in appointments:
        items.append({
            "id": appointment.id,
            "user_id": appointment.user_id,
            "start_time": appointment.start_time,
            "end_time": appointment.end_time,
            "status": appointment.status,
            "notes": appointment.notes,
            "created_at": appointment.created_at,
            "user": {
                "id": appointment.user.id,
                "phone": appointment.user.phone,
                "name": appointment.user.name,
                "birthdate": appointment.user.birthdate,
                "is_blacklisted": appointment.user.is_blacklisted
            } if appointment.user else None
        })

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.post("/appointments/update")
def update_appointment(
    request: AppointmentUpdateRequest,
    req: Request,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Update appointment"""

    appointment = db.query(Appointment).filter(
        Appointment.id == request.appointment_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    changes = {}
    if request.notes is not None:
        changes["notes"] = {"old": appointment.notes, "new": request.notes}
        appointment.notes = request.notes

    if request.status is not None:
        changes["status"] = {"old": appointment.status, "new": request.status}
        appointment.status = request.status

    db.commit()

    # Log the update
    audit_log_service.log_appointment_update(
        db=db,
        admin_phone=phone,
        appointment_id=request.appointment_id,
        changes=changes,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )

    return {"message": "Запис оновлено"}


@router.post("/appointments/create", response_model=AppointmentResponse)
async def admin_create_appointment(
    request: AdminAppointmentCreate,
    req: Request,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Create an appointment from the admin panel without user OTP."""

    if not slot_service.validate_slot_available(db, request.start_time):
        raise HTTPException(status_code=400, detail="Цей час вже зайнято")

    schedule = db.query(ScheduleConfig).first()
    if not schedule:
        raise HTTPException(status_code=500, detail="Розклад не налаштовано")

    user = db.query(User).filter(User.phone == request.phone).first()
    if user:
        if user.is_blacklisted:
            raise HTTPException(status_code=403, detail="Користувач у чорному списку")
        user.name = request.name
    else:
        user = User(
            phone=request.phone,
            name=request.name,
            birthdate=date(1900, 1, 1)
        )
        db.add(user)
        db.flush()
        track_user_registered()

    appointment = Appointment(
        user_id=user.id,
        start_time=request.start_time,
        end_time=request.start_time + timedelta(minutes=schedule.slot_duration),
        status=AppointmentStatus.BOOKED,
        notes=request.notes
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    track_appointment_created()
    invalidate_slots_cache()
    audit_log_service.log_action(
        db=db,
        admin_phone=phone,
        action="create_appointment",
        entity_type="appointment",
        entity_id=appointment.id,
        details={
            "user_id": user.id,
            "start_time": str(appointment.start_time),
            "created_from": "admin_schedule"
        },
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )
    await manager.notify_appointment_created({"id": appointment.id, "start_time": str(appointment.start_time)})
    await manager.notify_slots_updated()

    return appointment


@router.post("/appointments/cancel")
def admin_cancel_appointment(
    appointment_id: int,
    req: Request,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Cancel appointment (admin can cancel anytime)"""

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    # Get user details for notification
    from app.models.models import TelegramNotification
    user = appointment.user

    appointment.status = "cancelled"
    appointment.cancelled_by = "admin"

    # Create Telegram notification
    notification = TelegramNotification(
        phone=user.phone,
        notification_type="cancellation",
        message_data={
            "name": user.name,
            "start_time": appointment.start_time.isoformat(),
            "end_time": appointment.end_time.isoformat(),
            "cancelled_by": "admin",
            "appointment_id": appointment_id
        },
        sent=False
    )
    db.add(notification)
    db.commit()

    # Log the cancellation
    audit_log_service.log_appointment_cancel(
        db=db,
        admin_phone=phone,
        appointment_id=appointment_id,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )

    return {"message": "Запис скасовано"}


@router.delete("/appointments/{appointment_id}")
def admin_delete_appointment(
    appointment_id: int,
    req: Request,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Permanently delete appointment (admin only - for cleaning up cancelled records)"""

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    # Store details for audit log before deletion
    user_id = appointment.user_id
    start_time = appointment.start_time

    # Delete the appointment
    db.delete(appointment)
    db.commit()

    # Log the deletion
    audit_log_service.log_action(
        db=db,
        admin_phone=phone,
        action="delete_appointment",
        entity_type="appointment",
        entity_id=appointment_id,
        details={
            "user_id": user_id,
            "start_time": str(start_time),
            "reason": "Admin permanent deletion"
        },
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )

    return {"message": "Запис видалено назавжди"}


@router.post("/schedule", response_model=ScheduleConfigResponse)
def create_or_update_schedule(
    request: ScheduleConfigCreate,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Create or update schedule configuration"""

    schedule = db.query(ScheduleConfig).first()

    # Default to Mon-Fri if no working_days provided
    working_days = request.working_days if request.working_days is not None else [0, 1, 2, 3, 4]

    if schedule:
        schedule.start_time = request.start_time
        schedule.end_time = request.end_time
        schedule.slot_duration = request.slot_duration
        schedule.working_days = working_days
    else:
        schedule = ScheduleConfig(
            start_time=request.start_time,
            end_time=request.end_time,
            slot_duration=request.slot_duration,
            working_days=working_days
        )
        db.add(schedule)

    db.commit()
    db.refresh(schedule)

    return schedule


@router.get("/schedule", response_model=ScheduleConfigResponse)
def get_schedule(
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Get current schedule configuration"""

    schedule = db.query(ScheduleConfig).first()

    if not schedule:
        # Return default schedule if none exists
        return ScheduleConfigResponse(
            id=0,
            start_time="09:00",
            end_time="18:00",
            slot_duration=30,
            working_days=[0, 1, 2, 3, 4]
        )

    return schedule


@router.get("/days-off", response_model=List[DayOffResponse])
def get_days_off(
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Get all days off"""
    days_off = db.query(DayOff).all()
    return days_off


@router.post("/days-off", response_model=DayOffResponse)
def add_day_off(
    request: DayOffCreate,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Add day off"""

    # Check if already exists
    existing = db.query(DayOff).filter(DayOff.date == request.date).first()
    if existing:
        raise HTTPException(status_code=400, detail="Цей день вже додано")

    day_off = DayOff(date=request.date)
    db.add(day_off)
    db.commit()
    db.refresh(day_off)

    return day_off


@router.delete("/days-off/{day_off_id}")
def remove_day_off(
    day_off_id: int,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Remove day off"""

    day_off = db.query(DayOff).filter(DayOff.id == day_off_id).first()
    if not day_off:
        raise HTTPException(status_code=404, detail="Не знайдено")

    db.delete(day_off)
    db.commit()

    return {"message": "Вихідний видалено"}


@router.get("/blocked-slots", response_model=List[BlockedSlotResponse])
def get_blocked_slots(
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Get all blocked slots"""
    blocked_slots = db.query(BlockedSlot).all()
    return blocked_slots


@router.post("/block-slot", response_model=BlockedSlotResponse)
def block_slot(
    request: BlockedSlotCreate,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Block time slot"""

    blocked_slot = BlockedSlot(
        start_time=request.start_time,
        end_time=request.end_time
    )
    db.add(blocked_slot)
    db.commit()
    db.refresh(blocked_slot)

    return blocked_slot


@router.delete("/blocked-slots/{slot_id}")
def unblock_slot(
    slot_id: int,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Unblock time slot"""

    blocked_slot = db.query(BlockedSlot).filter(BlockedSlot.id == slot_id).first()
    if not blocked_slot:
        raise HTTPException(status_code=404, detail="Не знайдено")

    db.delete(blocked_slot)
    db.commit()

    return {"message": "Слот розблоковано"}


@router.post("/users/blacklist")
def update_blacklist(
    request: BlacklistRequest,
    req: Request,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Add or remove user from blacklist"""

    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    user.is_blacklisted = request.is_blacklisted
    db.commit()

    # Log the action
    audit_log_service.log_user_blacklist(
        db=db,
        admin_phone=phone,
        user_id=request.user_id,
        is_blacklisted=request.is_blacklisted,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )

    status = "додано до" if request.is_blacklisted else "видалено з"
    return {"message": f"Користувача {status} чорного списку"}


@router.post("/users/note")
def add_user_note(
    request: UserNoteRequest,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Add note to user"""

    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    user.notes = request.notes
    db.commit()

    return {"message": "Нотатку додано"}


@router.get("/users", response_model=dict)
def get_all_users(
    search: Optional[str] = Query(None),
    is_blacklisted: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Get all users with optional search, filters and pagination"""

    query = db.query(User)

    # Search by name or phone
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (User.name.ilike(search_pattern)) |
            (User.phone.like(search_pattern))
        )

    # Filter by blacklist status
    if is_blacklisted is not None:
        query = query.filter(User.is_blacklisted == is_blacklisted)

    # Get total count
    total = query.count()

    # Apply pagination
    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()

    # Convert to response models
    items = []
    for user in users:
        items.append({
            "id": user.id,
            "phone": user.phone,
            "email": user.email,
            "name": user.name,
            "birthdate": user.birthdate,
            "is_blacklisted": user.is_blacklisted,
            "email_verified": user.email_verified,
            "notes": user.notes,
            "created_at": user.created_at
        })

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/users/{user_id}/appointments")
def get_user_appointments(
    user_id: int,
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Get all appointments for a specific user"""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    appointments = db.query(Appointment).filter(
        Appointment.user_id == user_id
    ).order_by(Appointment.start_time.desc()).all()

    return {
        "user": {
            "id": user.id,
            "phone": user.phone,
            "name": user.name,
            "birthdate": user.birthdate
        },
        "appointments": [
            {
                "id": apt.id,
                "start_time": apt.start_time,
                "end_time": apt.end_time,
                "status": apt.status,
                "notes": apt.notes,
                "created_at": apt.created_at
            }
            for apt in appointments
        ]
    }


@router.get("/report")
def generate_report(
    from_date: date = Query(...),
    to_date: date = Query(...),
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Generate report for date range"""

    appointments = db.query(Appointment).filter(
        Appointment.start_time >= datetime.combine(from_date, datetime.min.time()),
        Appointment.start_time <= datetime.combine(to_date, datetime.max.time())
    ).order_by(Appointment.start_time).all()
    free_slots = slot_service.get_available_slots(db, from_date, to_date, include_past=True)
    report_rows = (
        [{"type": "appointment", "appointment": appointment, "start_time": appointment.start_time, "end_time": appointment.end_time}
         for appointment in appointments] +
        [{"type": "free_slot", "slot": slot, "start_time": slot.start_time, "end_time": slot.end_time}
         for slot in free_slots]
    )
    report_rows.sort(key=lambda row: (row["start_time"], 0 if row["type"] == "appointment" else 1))

    # Calculate statistics
    total_appointments = len(appointments)
    booked_count = sum(1 for a in appointments if a.status == 'booked')
    cancelled_count = sum(1 for a in appointments if a.status == 'cancelled')
    unique_patients = len(set(a.user_id for a in appointments))

    # Generate modern dark-themed HTML report
    html = f"""
    <!DOCTYPE html>
    <html lang="uk">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Звіт про записи - {from_date.strftime('%d.%m.%Y')} - {to_date.strftime('%d.%m.%Y')}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                color: #e2e8f0;
                padding: 2rem;
                line-height: 1.6;
            }}

            .container {{
                max-width: 1400px;
                margin: 0 auto;
                background: #1e293b;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
                overflow: hidden;
            }}

            .header {{
                background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%);
                padding: 2.5rem 2rem;
                color: white;
            }}

            .header h1 {{
                font-size: 2rem;
                font-weight: 800;
                margin-bottom: 0.5rem;
                letter-spacing: -0.02em;
            }}

            .header .period {{
                font-size: 1.1rem;
                opacity: 0.95;
                font-weight: 500;
            }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 1.5rem;
                padding: 2rem;
                background: #0f172a;
            }}

            .stat-card {{
                background: #1e293b;
                border: 1.5px solid #334155;
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
                transition: all 0.3s ease;
            }}

            .stat-card:hover {{
                border-color: #06b6d4;
                transform: translateY(-2px);
                box-shadow: 0 8px 24px rgba(6, 182, 212, 0.2);
            }}

            .stat-card .icon {{
                font-size: 2.5rem;
                margin-bottom: 0.5rem;
            }}

            .stat-card .value {{
                font-size: 2.5rem;
                font-weight: 800;
                color: #06b6d4;
                margin-bottom: 0.25rem;
            }}

            .stat-card .label {{
                font-size: 0.875rem;
                color: #94a3b8;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}

            .content {{
                padding: 2rem;
            }}

            .section-title {{
                font-size: 1.25rem;
                font-weight: 700;
                color: #f1f5f9;
                margin-bottom: 1.5rem;
                padding-bottom: 0.75rem;
                border-bottom: 2px solid #334155;
            }}

            .table-container {{
                overflow-x: auto;
                border-radius: 12px;
                border: 1.5px solid #334155;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                background: #0f172a;
            }}

            thead {{
                background: linear-gradient(135deg, #334155 0%, #475569 100%);
            }}

            th {{
                padding: 1rem;
                text-align: left;
                font-weight: 700;
                font-size: 0.875rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: #f1f5f9;
                border-bottom: 2px solid #06b6d4;
            }}

            td {{
                padding: 1rem;
                border-bottom: 1px solid #334155;
                font-size: 0.9rem;
                color: #cbd5e1;
            }}

            tbody tr {{
                transition: all 0.2s ease;
            }}

            tbody tr:hover {{
                background: #1e293b;
            }}

            .day-separator td {{
                background: #0e7490;
                color: white;
                font-weight: 800;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                border-top: 2px solid #67e8f9;
                border-bottom: 2px solid #67e8f9;
                padding: 0.75rem 1rem;
            }}

            .status-badge {{
                display: inline-block;
                padding: 0.35rem 0.75rem;
                border-radius: 12px;
                font-size: 0.75rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}

            .status-booked {{
                background: rgba(6, 182, 212, 0.2);
                color: #06b6d4;
                border: 1px solid rgba(6, 182, 212, 0.4);
            }}

            .status-cancelled {{
                background: rgba(239, 68, 68, 0.2);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.4);
            }}

            .actions {{
                display: flex;
                gap: 1rem;
                margin-bottom: 2rem;
            }}

            .btn {{
                padding: 0.875rem 1.75rem;
                border: none;
                border-radius: 10px;
                font-weight: 700;
                font-size: 0.9rem;
                cursor: pointer;
                transition: all 0.3s ease;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            }}

            .btn-print {{
                background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%);
                color: white;
            }}

            .btn-print:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(6, 182, 212, 0.4);
            }}

            .footer {{
                padding: 2rem;
                text-align: center;
                color: #64748b;
                font-size: 0.875rem;
                border-top: 1px solid #334155;
            }}

            @media print {{
                body {{
                    background: white !important;
                    padding: 0 !important;
                    color: #000 !important;
                }}

                .container {{
                    box-shadow: none !important;
                    border-radius: 0 !important;
                    background: white !important;
                }}

                .header {{
                    background: white !important;
                    color: #000 !important;
                    border-bottom: 3px solid #06b6d4;
                    page-break-after: avoid;
                }}

                .header h1 {{
                    color: #06b6d4 !important;
                }}

                .header .period {{
                    color: #475569 !important;
                }}

                .stats-grid {{
                    background: white !important;
                    padding: 1.5rem 0 !important;
                    page-break-inside: avoid;
                    page-break-after: avoid;
                }}

                .stat-card {{
                    background: white !important;
                    border: 2px solid #cbd5e1 !important;
                    box-shadow: none !important;
                    page-break-inside: avoid;
                }}

                .stat-card:hover {{
                    transform: none !important;
                    box-shadow: none !important;
                }}

                .stat-card .value {{
                    color: #06b6d4 !important;
                }}

                .stat-card .label {{
                    color: #475569 !important;
                }}

                .content {{
                    background: white !important;
                    padding: 1.5rem 0 !important;
                }}

                .section-title {{
                    color: #0f172a !important;
                    border-bottom: 2px solid #cbd5e1 !important;
                    page-break-after: avoid;
                }}

                .table-container {{
                    border: 2px solid #cbd5e1 !important;
                    border-radius: 0 !important;
                }}

                table {{
                    background: white !important;
                    page-break-inside: auto;
                }}

                thead {{
                    background: #f1f5f9 !important;
                    display: table-header-group;
                }}

                th {{
                    color: #0f172a !important;
                    background: #f1f5f9 !important;
                    border-bottom: 2px solid #06b6d4 !important;
                }}

                tbody tr {{
                    page-break-inside: avoid;
                    page-break-after: auto;
                }}

                tbody tr:hover {{
                    background: white !important;
                }}

                .day-separator td {{
                    background: #e0f2fe !important;
                    color: #0c4a6e !important;
                    border-top: 2px solid #06b6d4 !important;
                    border-bottom: 1px solid #bae6fd !important;
                }}

                td {{
                    color: #1e293b !important;
                    border-bottom: 1px solid #e2e8f0 !important;
                }}

                .status-badge {{
                    border: 1px solid #cbd5e1 !important;
                    background: white !important;
                }}

                .status-booked {{
                    color: #06b6d4 !important;
                    border-color: #06b6d4 !important;
                }}

                .status-cancelled {{
                    color: #dc3545 !important;
                    border-color: #dc3545 !important;
                }}

                .actions {{
                    display: none !important;
                }}

                /* Hide emojis in print */
                .icon {{
                    display: none !important;
                }}

                .emoji-icon {{
                    display: none !important;
                }}

                .header h1::before {{
                    content: '' !important;
                }}

                /* Better table styling for print */
                table {{
                    font-size: 10pt !important;
                }}

                th {{
                    padding: 8pt 6pt !important;
                    font-size: 9pt !important;
                }}

                td {{
                    padding: 8pt 6pt !important;
                    font-size: 9pt !important;
                }}

                /* Compact stats for print */
                .stats-grid {{
                    grid-template-columns: repeat(4, 1fr) !important;
                    gap: 0.5rem !important;
                }}

                .stat-card {{
                    padding: 0.75rem !important;
                }}

                .stat-card .value {{
                    font-size: 1.5rem !important;
                }}

                .stat-card .label {{
                    font-size: 0.7rem !important;
                }}

                /* Optimize spacing for print */
                .header {{
                    padding: 1rem !important;
                }}

                .header h1 {{
                    font-size: 1.5rem !important;
                    margin-bottom: 0.25rem !important;
                }}

                .header .period {{
                    font-size: 0.9rem !important;
                }}

                .section-title {{
                    font-size: 1rem !important;
                    margin-bottom: 0.75rem !important;
                    padding-bottom: 0.5rem !important;
                }}

                /* Ensure proper table width */
                .table-container {{
                    overflow: visible !important;
                }}

                /* Page margins */
                @page {{
                    margin: 1.5cm;
                    size: A4 landscape;
                }}

                /* Text optimization */
                body {{
                    -webkit-print-color-adjust: exact !important;
                    print-color-adjust: exact !important;
                }}

                /* Prevent orphans and widows */
                p, h1, h2, h3, td {{
                    orphans: 3;
                    widows: 3;
                }}

                /* Better table rendering */
                table {{
                    border-collapse: collapse !important;
                }}

                tbody {{
                    display: table-row-group !important;
                }}

                /* Ensure no blank pages */
                .container {{
                    max-width: 100% !important;
                }}

                .footer {{
                    background: white !important;
                    color: #64748b !important;
                    border-top: 1px solid #cbd5e1 !important;
                    page-break-inside: avoid;
                }}

                /* Remove page breaks in the middle of cards */
                .stat-card, .section-title, thead {{
                    page-break-inside: avoid;
                }}
            }}

            @media (max-width: 768px) {{
                body {{
                    padding: 1rem;
                }}
                .header {{
                    padding: 1.5rem 1rem;
                }}
                .header h1 {{
                    font-size: 1.5rem;
                }}
                .stats-grid {{
                    grid-template-columns: 1fr;
                    gap: 1rem;
                    padding: 1rem;
                }}
                .content {{
                    padding: 1rem;
                }}
                th, td {{
                    padding: 0.75rem 0.5rem;
                    font-size: 0.8rem;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><span class="emoji-icon">📊</span> Звіт про записи на прийом</h1>
                <p class="period">Період: {from_date.strftime('%d.%m.%Y')} - {to_date.strftime('%d.%m.%Y')}</p>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="icon">📅</div>
                    <div class="value">{total_appointments}</div>
                    <div class="label">Всього записів</div>
                </div>
                <div class="stat-card">
                    <div class="icon">✅</div>
                    <div class="value">{booked_count}</div>
                    <div class="label">Заброньовано</div>
                </div>
                <div class="stat-card">
                    <div class="icon">❌</div>
                    <div class="value">{cancelled_count}</div>
                    <div class="label">Скасовано</div>
                </div>
                <div class="stat-card">
                    <div class="icon">👥</div>
                    <div class="value">{unique_patients}</div>
                    <div class="label">Унікальних пацієнтів</div>
                </div>
            </div>

            <div class="content">
                <div class="actions">
                    <button class="btn btn-print" onclick="window.print()">🖨️ Роздрукувати звіт</button>
                </div>

                <h2 class="section-title">Детальна інформація про записи</h2>

                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Дата та час</th>
                                <th>Пацієнт</th>
                                <th>Телефон</th>
                                <th>Дата народження</th>
                                <th>Вік</th>
                                <th>Нотатки (запис)</th>
                                <th>Нотатки (пацієнт)</th>
                            </tr>
                        </thead>
                        <tbody>
    """

    current_day = None
    item_number = 0

    for row in report_rows:
        start_time = row["start_time"]
        row_day = start_time.date()
        if row_day != current_day:
            current_day = row_day
            html += f"""
                            <tr class="day-separator">
                                <td colspan="8">{start_time.strftime('%d.%m.%Y')}</td>
                            </tr>
        """

        item_number += 1
        if row["type"] == "free_slot":
            end_time = row["end_time"]
            html += f"""
                            <tr>
                                <td><strong>{item_number}</strong></td>
                                <td><strong>{start_time.strftime('%d.%m.%Y')}</strong><br>{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}</td>
                                <td></td>
                                <td></td>
                                <td></td>
                                <td></td>
                                <td></td>
                                <td></td>
                            </tr>
        """
            continue

        appointment = row["appointment"]
        user = appointment.user
        birthdate_text, age_text = format_report_birthdate_and_age(user)

        html += f"""
                            <tr>
                                <td><strong>{item_number}</strong></td>
                                <td><strong>{appointment.start_time.strftime('%d.%m.%Y')}</strong><br>{appointment.start_time.strftime('%H:%M')} - {appointment.end_time.strftime('%H:%M')}</td>
                                <td><strong>{escape(user.name)}</strong></td>
                                <td>{escape(user.phone)}</td>
                                <td>{birthdate_text}</td>
                                <td>{age_text}</td>
                                <td>{escape(appointment.notes) if appointment.notes else '-'}</td>
                                <td>{escape(user.notes) if user.notes else '-'}</td>
                            </tr>
        """

    html += f"""
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="footer">
                <p>Згенеровано: {datetime.now().strftime('%d.%m.%Y о %H:%M')}</p>
                <p>Медичний центр - Система управління записами</p>
            </div>
        </div>
    </body>
    </html>
    """

    return {"html": html}


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Get dashboard statistics"""

    now = datetime.now()
    today_start = datetime.combine(now.date(), datetime.min.time())
    today_end = datetime.combine(now.date(), datetime.max.time())
    week_start = today_start - timedelta(days=now.weekday())
    month_start = datetime(now.year, now.month, 1)

    # Total counts
    total_appointments = db.query(Appointment).count()
    total_users = db.query(User).count()

    # Appointments by time period
    appointments_today = db.query(Appointment).filter(
        Appointment.start_time >= today_start,
        Appointment.start_time <= today_end
    ).count()

    appointments_this_week = db.query(Appointment).filter(
        Appointment.start_time >= week_start
    ).count()

    appointments_this_month = db.query(Appointment).filter(
        Appointment.start_time >= month_start
    ).count()

    # Appointments by status
    completed_appointments = db.query(Appointment).filter(
        Appointment.status == 'booked',
        Appointment.start_time < now
    ).count()

    cancelled_appointments = db.query(Appointment).filter(
        Appointment.status == 'cancelled'
    ).count()

    upcoming_appointments = db.query(Appointment).filter(
        Appointment.status == 'booked',
        Appointment.start_time > now
    ).count()

    # Users stats
    active_users = db.query(User).filter(User.is_blacklisted == False).count()
    blacklisted_users = db.query(User).filter(User.is_blacklisted == True).count()

    # Status breakdown
    status_breakdown = {}
    status_counts = db.query(
        Appointment.status,
        func.count(Appointment.id)
    ).group_by(Appointment.status).all()

    for status, count in status_counts:
        status_breakdown[status] = count

    # Appointments by day (next 7 days)
    appointments_by_day = []
    day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']

    for i in range(0, 7):
        day_date = now.date() + timedelta(days=i)
        day_start = datetime.combine(day_date, datetime.min.time())
        day_end = datetime.combine(day_date, datetime.max.time())

        count = db.query(Appointment).filter(
            Appointment.start_time >= day_start,
            Appointment.start_time <= day_end
        ).count()

        appointments_by_day.append({
            'date': day_date.strftime('%Y-%m-%d'),
            'day': day_names[day_date.weekday()],
            'count': count
        })

    return DashboardStats(
        total_appointments=total_appointments,
        total_users=total_users,
        appointments_today=appointments_today,
        appointments_this_week=appointments_this_week,
        appointments_this_month=appointments_this_month,
        completed_appointments=completed_appointments,
        cancelled_appointments=cancelled_appointments,
        active_users=active_users,
        blacklisted_users=blacklisted_users,
        upcoming_appointments=upcoming_appointments,
        status_breakdown=status_breakdown,
        appointments_by_day=appointments_by_day
    )


@router.get("/export/pdf")
def export_appointments_pdf(
    from_date: date = Query(...),
    to_date: date = Query(...),
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Export appointments to PDF"""

    appointments = db.query(Appointment).filter(
        Appointment.start_time >= datetime.combine(from_date, datetime.min.time()),
        Appointment.start_time <= datetime.combine(to_date, datetime.max.time())
    ).order_by(Appointment.start_time).all()
    free_slots = slot_service.get_available_slots(db, from_date, to_date, include_past=True)

    # Load user relationships
    for appointment in appointments:
        appointment.user

    # Generate PDF
    pdf_buffer = ReportGenerator.generate_pdf_report(
        appointments,
        from_date.strftime('%d.%m.%Y'),
        to_date.strftime('%d.%m.%Y'),
        free_slots
    )

    filename = f"appointments_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/excel")
def export_appointments_excel(
    from_date: date = Query(...),
    to_date: date = Query(...),
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Export appointments to Excel"""

    appointments = db.query(Appointment).filter(
        Appointment.start_time >= datetime.combine(from_date, datetime.min.time()),
        Appointment.start_time <= datetime.combine(to_date, datetime.max.time())
    ).order_by(Appointment.start_time).all()
    free_slots = slot_service.get_available_slots(db, from_date, to_date, include_past=True)

    # Load user relationships
    for appointment in appointments:
        appointment.user

    # Generate Excel
    excel_buffer = ReportGenerator.generate_excel_report(
        appointments,
        from_date.strftime('%d.%m.%Y'),
        to_date.strftime('%d.%m.%Y'),
        free_slots
    )

    filename = f"appointments_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        excel_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )



@router.get("/audit-logs", response_model=dict)
def get_audit_logs(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    phone: str = Depends(verify_admin_session),
    db: Session = Depends(get_db)
):
    """Get audit logs with filters and pagination"""

    query = db.query(AuditLog)

    # Date filters
    if from_date:
        query = query.filter(AuditLog.timestamp >= datetime.combine(from_date, datetime.min.time()))

    if to_date:
        query = query.filter(AuditLog.timestamp <= datetime.combine(to_date, datetime.max.time()))

    # Action filter
    if action:
        query = query.filter(AuditLog.action == action)

    # Entity type filter
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)

    # Get total count
    total = query.count()

    # Apply pagination
    logs = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()

    return {
        "items": logs,
        "total": total,
        "skip": skip,
        "limit": limit
    }
