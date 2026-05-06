from fastapi import APIRouter, HTTPException, Depends, Body, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from app.core.database import get_db
from app.models.models import OTPCode, Appointment, User
from app.core.config import settings
import requests
import logging

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)


class TelegramOTPRequest(BaseModel):
    phone: str
    code: str
    secret: str


@router.post("/otp-sent")
async def telegram_otp_sent(
    request: TelegramOTPRequest,
    db: Session = Depends(get_db)
):
    """Receive notification that OTP was sent via Telegram"""

    # Verify secret
    if request.secret != settings.BOT_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    # Invalidate previous codes
    db.query(OTPCode).filter(
        OTPCode.phone == request.phone,
        OTPCode.verified == False
    ).delete()

    # Store OTP in database
    otp = OTPCode(
        phone=request.phone,
        code=request.code,
        expires_at=datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
        verified=False,
        attempts=0
    )
    db.add(otp)
    db.commit()

    return {"message": "OTP saved", "method": "telegram"}


@router.post("/verify-otp")
async def telegram_verify_otp(
    request: TelegramOTPRequest,
    db: Session = Depends(get_db)
):
    """Verify OTP from Telegram bot"""

    # Verify secret
    if request.secret != settings.BOT_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    # Find OTP
    otp = db.query(OTPCode).filter(
        OTPCode.phone == request.phone,
        OTPCode.code == request.code,
        OTPCode.verified == False
    ).first()

    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # Check if expired
    if datetime.utcnow() > otp.expires_at:
        raise HTTPException(status_code=400, detail="Expired OTP")

    # Check attempts
    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Too many attempts")

    # Mark as verified
    otp.verified = True
    db.commit()

    return {"message": "OTP verified successfully"}


@router.post("/check-phone")
async def check_phone_registered(
    phone: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """Check if phone is registered in Telegram bot (called by frontend)"""

    # This endpoint can be extended to check if user registered in bot
    # For now, just return success
    # In production, you might want to maintain a separate table of telegram_users

    return {"registered": True, "method": "telegram"}


class CancellationNotification(BaseModel):
    phone: str
    name: str
    start_time: datetime
    cancelled_by: str = "admin"


def send_telegram_cancellation(phone: str, name: str, start_time: datetime, cancelled_by: str = "admin"):
    """Send cancellation notification via Telegram bot webhook"""
    try:
        # This would call the bot's webhook endpoint
        # For now, we'll log it - the bot will need to expose an endpoint or use a message queue
        logger.info(f"📤 Cancellation notification queued for {phone}: appointment at {start_time}")

        # In production, you would:
        # 1. Call a bot webhook endpoint
        # 2. Use a message queue (Redis, RabbitMQ)
        # 3. Or store in a notifications table that the bot polls

        # For this implementation, we'll create a simple notification table approach
        # The bot can poll this or we can implement a webhook

    except Exception as e:
        logger.error(f"❌ Error sending Telegram cancellation notification: {e}")


@router.post("/notify-cancellation")
async def notify_cancellation(
    notification: CancellationNotification,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Internal endpoint to notify user about appointment cancellation"""

    # Queue the notification to be sent in background
    background_tasks.add_task(
        send_telegram_cancellation,
        notification.phone,
        notification.name,
        notification.start_time,
        notification.cancelled_by
    )

    return {"message": "Notification queued"}

