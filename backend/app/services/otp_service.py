from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models.models import OTPCode
from app.core.config import settings
import httpx
import os
import random
import string


class OTPService:
    def __init__(self):
        self.expiry_minutes = settings.OTP_EXPIRY_MINUTES
        self.max_attempts = settings.OTP_MAX_ATTEMPTS
        self.max_otp_per_hour = 3

    def generate_otp(self, length: int = 6) -> str:
        """Generate a random OTP code"""
        return ''.join(random.choices(string.digits, k=length))

    def check_rate_limit(self, db: Session, phone: str) -> tuple[bool, int]:
        """
        Check if user has exceeded OTP rate limit.
        Returns (is_allowed, count_in_last_hour)
        Optimized: Single query with count
        """
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)

        count = db.query(OTPCode).filter(
            OTPCode.phone == phone,
            OTPCode.created_at > one_hour_ago
        ).count()

        return count < self.max_otp_per_hour, count

    def send_otp(self, db: Session, phone: str) -> dict:
        """
        Generate and send OTP code.
        Returns dict with success status and optional error message.
        Optimized: Combined operations, reduced DB calls
        """

        # Test user bypass - no SMS required
        if phone == "+380999999999":
            # Single operation: delete old + add new in one transaction
            db.query(OTPCode).filter(
                OTPCode.phone == phone,
                OTPCode.verified == False
            ).delete()

            # Create auto-verified OTP for test user with 7-day validity
            otp = OTPCode(
                phone=phone,
                code="111111",
                expires_at=datetime.utcnow() + timedelta(days=7),
                verified=True,
                attempts=0,
                created_at=datetime.utcnow()
            )
            db.add(otp)
            db.commit()
            return {"success": True, "code": "111111"}

        # Check rate limit before generating OTP
        is_allowed, count = self.check_rate_limit(db, phone)
        if not is_allowed:
            return {
                "success": False,
                "error": "rate_limit_exceeded",
                "count": count,
                "max": self.max_otp_per_hour
            }

        # Invalidate previous codes (single DELETE query)
        db.query(OTPCode).filter(
            OTPCode.phone == phone,
            OTPCode.verified == False
        ).delete()

        # Generate new code
        code = self.generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=self.expiry_minutes)
        created_at = datetime.utcnow()

        # Save to database
        otp = OTPCode(
            phone=phone,
            code=code,
            expires_at=expires_at,
            verified=False,
            attempts=0,
            created_at=created_at
        )
        db.add(otp)
        db.commit()

        # OTP is saved to database
        # User will get code from Telegram bot by clicking button
        # Bot reads from same database and shows the code
        return {"success": True, "code": code}

    def _send_via_telegram(self, phone: str, code: str) -> bool:
        """Send OTP via Telegram bot"""
        try:
            # Get bot URL from environment or use local default
            bot_url = os.getenv('TELEGRAM_BOT_URL', 'http://localhost:5000')

            # Call bot's webhook/API to send OTP
            response = httpx.post(
                f"{bot_url}/send-otp",
                json={
                    "phone": phone,
                    "code": code,
                    "secret": settings.BOT_SECRET
                },
                timeout=5.0
            )

            if response.status_code == 200:
                return True

            return False
        except Exception as e:
            # Log error but don't fail - fallback to SMS
            print(f"Telegram bot error: {e}")
            return False

    def verify_otp(self, db: Session, phone: str, code: str) -> bool:
        """
        Verify OTP code.
        Optimized: Single query with all filters
        """

        # Test user bypass - any code works
        if phone == "+380999999999":
            # Find or create verified OTP
            otp = db.query(OTPCode).filter(
                OTPCode.phone == phone,
                OTPCode.verified == True
            ).first()

            if not otp:
                otp = OTPCode(
                    phone=phone,
                    code="111111",
                    expires_at=datetime.utcnow() + timedelta(hours=24),
                    verified=True,
                    attempts=0,
                    created_at=datetime.utcnow()
                )
                db.add(otp)
                db.commit()

            return True

        # Optimized: Single query with all conditions
        otp = db.query(OTPCode).filter(
            OTPCode.phone == phone,
            OTPCode.code == code,
            OTPCode.verified == False,
            OTPCode.expires_at > datetime.utcnow(),  # Check expiration in query
            OTPCode.attempts < self.max_attempts      # Check attempts in query
        ).first()

        if not otp:
            return False

        # Verify code
        if otp.code == code:
            otp.verified = True
            # Extend expiration to 7 days for session validity
            otp.expires_at = datetime.utcnow() + timedelta(days=7)
            db.commit()
            return True

        # If code doesn't match, increment attempts
        otp.attempts += 1
        db.commit()
        return False

    def is_verified(self, db: Session, phone: str) -> bool:
        """
        Check if phone number has been verified recently.
        Optimized: Single query with exists()
        """
        return db.query(
            db.query(OTPCode).filter(
                OTPCode.phone == phone,
                OTPCode.verified == True,
                OTPCode.expires_at > datetime.utcnow()
            ).exists()
        ).scalar()

    def cleanup_expired_otps(self, db: Session) -> int:
        """
        Clean up expired OTP codes older than 24 hours.
        Returns number of deleted records.
        Should be called periodically (e.g., daily cron job)
        """
        threshold = datetime.utcnow() - timedelta(hours=24)

        deleted = db.query(OTPCode).filter(
            OTPCode.expires_at < threshold
        ).delete()

        db.commit()
        return deleted

    def get_active_otp(self, db: Session, phone: str) -> OTPCode | None:
        """
        Get active (non-verified, non-expired) OTP for a phone.
        Optimized: Single query with all conditions
        """
        return db.query(OTPCode).filter(
            OTPCode.phone == phone,
            OTPCode.verified == False,
            OTPCode.expires_at > datetime.utcnow()
        ).order_by(OTPCode.created_at.desc()).first()


otp_service = OTPService()
