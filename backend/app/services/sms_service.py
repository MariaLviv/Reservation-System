import random
import string


class SMSService:
    """SMS Service - Twilio removed, OTP handled via Telegram bot only"""

    def __init__(self):
        pass

    def send_otp(self, to_phone: str, code: str) -> bool:
        """OTP is sent via Telegram bot, not SMS"""
        # This method is kept for compatibility but does nothing
        # OTP codes are retrieved from database by Telegram bot
        print(f"SMS service disabled - OTP for {to_phone}: {code} (use Telegram bot)")
        return True

    def send_reminder(self, to_phone: str, appointment_time: str) -> bool:
        """Appointment reminders via Telegram bot, not SMS"""
        # This method is kept for compatibility
        print(f"SMS service disabled - Reminder for {to_phone} at {appointment_time} (use Telegram bot)")
        return True

    @staticmethod
    def generate_otp() -> str:
        """Generate 6-digit OTP code"""
        return ''.join(random.choices(string.digits, k=6))


sms_service = SMSService()
