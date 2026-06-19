"""
Telegram OTP Bot - Enhanced Version
Features:
- Database persistence for user phones
- Connection pooling
- Rate limiting
- Appointment management
- Better error handling and logging
- Health checks and metrics
"""

import os
import logging
import warnings
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
import random
from contextlib import contextmanager

# Suppress pkg_resources deprecation warning from APScheduler
warnings.filterwarnings('ignore', message='.*pkg_resources is deprecated.*')

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, Bot
    from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
    import psycopg2
    from psycopg2 import pool
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz
except ImportError:
    import subprocess
    subprocess.check_call(['pip', 'install', 'python-telegram-bot==13.15', 'psycopg2-binary', 'python-dotenv', 'APScheduler', 'pytz'])
    from dotenv import load_dotenv
    load_dotenv()
    from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, Bot
    from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
    import psycopg2
    from psycopg2 import pool
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz

# Configure logging with colors and better format
class ColoredFormatter(logging.Formatter):
    """Colored log formatter"""

    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    FORMATS = {
        logging.DEBUG: grey + "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s" + reset,
        logging.INFO: blue + "%(asctime)s - [%(levelname)s] %(message)s" + reset,
        logging.WARNING: yellow + "%(asctime)s - [%(levelname)s] %(message)s" + reset,
        logging.ERROR: red + "%(asctime)s - [%(levelname)s] %(message)s" + reset,
        logging.CRITICAL: bold_red + "%(asctime)s - [%(levelname)s] %(message)s" + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

# Configure logging
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler]
)
logger = logging.getLogger(__name__)


TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
# Verify we're using the correct database
#print(f"🔍 Database URL: {DATABASE_URL[:50]}...")
if 'supabase.com' in DATABASE_URL:
    print("✅ Using Supabase database (matches backend)")
elif 'heliumdb' in DATABASE_URL:
    print("⚠️  WARNING: Using heliumdb - OTP verification will FAIL!")
    print("⚠️  Bot must use Supabase database to match backend")
else:
    print(f"⚠️  Using database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'unknown'}")

OTP_LENGTH: int = 6
OTP_EXPIRY_MINUTES: int = 5
MAX_OTP_PER_HOUR: int = 3
MAX_FAILED_ATTEMPTS: int = 5

# Conversation states for user registration
STATE_WAITING_LAST_NAME = 'waiting_last_name'
STATE_WAITING_FIRST_NAME = 'waiting_first_name'
STATE_WAITING_BIRTHDATE = 'waiting_birthdate'

# Global connection pool
connection_pool: Optional[pool.SimpleConnectionPool] = None


def init_connection_pool(minconn: int = 1, maxconn: int = 10) -> None:
    """Initialize database connection pool"""
    global connection_pool
    try:
        connection_pool = pool.SimpleConnectionPool(
            minconn,
            maxconn,
            DATABASE_URL,
            sslmode='prefer'
        )
        logger.info(f"✅ Connection pool initialized (min={minconn}, max={maxconn})")
    except Exception as e:
        logger.error(f"❌ Failed to initialize connection pool: {e}")
        raise


@contextmanager
def get_db_connection():
    """Context manager for database connections with health check"""
    conn = None
    try:
        if connection_pool is None:
            init_connection_pool()

        conn = connection_pool.getconn()

        # Health check - test connection
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.fetchone()
        cursor.close()

        yield conn

    except psycopg2.OperationalError as e:
        logger.error(f"❌ Database connection error: {e}. Attempting to reconnect...")
        # Try to reinitialize pool
        try:
            init_connection_pool()
            conn = connection_pool.getconn()
            yield conn
        except Exception as reconnect_error:
            logger.error(f"❌ Reconnection failed: {reconnect_error}")
            raise
    except Exception as e:
        logger.error(f"❌ Database error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            connection_pool.putconn(conn)


def init_database_tables() -> bool:
    """Create required tables if they don't exist"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Create telegram_users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS public.telegram_users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    phone VARCHAR(20) NOT NULL,
                    username VARCHAR(255),
                    registered_at TIMESTAMP DEFAULT NOW(),
                    last_active TIMESTAMP DEFAULT NOW()
                )
            """)

            # Create otp_codes table (matches backend model)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS public.otp_codes (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(20) NOT NULL,
                    code VARCHAR(10) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    verified BOOLEAN DEFAULT FALSE,
                    attempts INTEGER DEFAULT 0
                )
            """)

            # Create bot_events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS public.bot_events (
                    id SERIAL PRIMARY KEY,
                    event_type VARCHAR(50) NOT NULL,
                    telegram_id BIGINT NOT NULL,
                    phone VARCHAR(20),
                    details TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Create telegram_notifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS public.telegram_notifications (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(20) NOT NULL,
                    notification_type VARCHAR(50) NOT NULL,
                    message_data JSONB,
                    sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    sent_at TIMESTAMP
                )
            """)

            # Note: appointments and users tables are created by backend
            # No need to create them here

            # Create indexes for better performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_otp_phone ON public.otp_codes(phone);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_otp_expires ON public.otp_codes(expires_at);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_telegram_users_telegram_id ON public.telegram_users(telegram_id);
            """)

            conn.commit()
            cursor.close()
            logger.info("✅ Database tables initialized successfully")
            return True

    except Exception as e:
        logger.error(f"❌ Error initializing database tables: {e}")
        return False


def save_user_phone(telegram_id: int, phone: str, username: Optional[str] = None) -> bool:
    """Save user phone to database for persistence"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Upsert user phone
            cursor.execute("""
                INSERT INTO public.telegram_users (telegram_id, phone, username)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    phone = EXCLUDED.phone,
                    username = EXCLUDED.username,
                    last_active = NOW()
            """, (telegram_id, phone, username))

            conn.commit()
            cursor.close()
            logger.info(f"✅ User phone saved: telegram_id={telegram_id}, phone={phone}")
            return True

    except Exception as e:
        logger.error(f"❌ Error saving user phone: {e}")
        return False


def get_user_phone(telegram_id: int) -> Optional[str]:
    """Get user phone from database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT phone FROM public.telegram_users WHERE telegram_id = %s",
                (telegram_id,)
            )
            result = cursor.fetchone()
            cursor.close()

            if result:
                logger.info(f"📱 Retrieved phone for telegram_id={telegram_id}")
                return result[0]
            return None

    except Exception as e:
        logger.error(f"❌ Error getting user phone: {e}")
        return None


def check_user_profile_exists(phone: str) -> bool:
    """Check if user has a profile in the users table"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM public.users WHERE phone = %s",
                (phone,)
            )
            result = cursor.fetchone()
            cursor.close()

            exists = result is not None
            logger.info(f"👤 User profile exists check for {phone}: {exists}")
            return exists

    except Exception as e:
        logger.error(f"❌ Error checking user profile: {e}")
        return False


def save_user_profile(phone: str, name: str, birthdate: str) -> bool:
    """Save user profile to users table"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO public.users (phone, name, birthdate, email_verified, is_blacklisted)
                VALUES (%s, %s, %s, false, false)
                ON CONFLICT (phone)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    birthdate = EXCLUDED.birthdate
            """, (phone, name, birthdate))

            conn.commit()
            cursor.close()
            logger.info(f"✅ User profile saved: phone={phone}, name={name}")
            return True

    except Exception as e:
        logger.error(f"❌ Error saving user profile: {e}")
        return False


def check_rate_limit(phone: str) -> Tuple[bool, int]:
    """
    Check if user exceeded OTP rate limit. Returns (is_allowed, count_last_hour)
    Optimized: Single query using created_at field
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)

            # Optimized: Use created_at for accurate rate limiting
            cursor.execute("""
                SELECT COUNT(*) FROM public.otp_codes
                WHERE phone = %s AND created_at > %s
            """, (phone, one_hour_ago))

            count = cursor.fetchone()[0]
            cursor.close()

            is_allowed = count < MAX_OTP_PER_HOUR
            logger.info(f"🔒 Rate limit check for {phone}: {count}/{MAX_OTP_PER_HOUR} (allowed={is_allowed})")
            return is_allowed, count

    except Exception as e:
        logger.error(f"❌ Error checking rate limit: {e}")
        return True, 0  # Allow on error


def log_bot_event(event_type: str, telegram_id: int, phone: Optional[str] = None, details: Optional[str] = None) -> None:
    """Log bot events for analytics"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO public.bot_events (event_type, telegram_id, phone, details)
                VALUES (%s, %s, %s, %s)
            """, (event_type, telegram_id, phone, details))

            conn.commit()
            cursor.close()
            logger.debug(f"📊 Event logged: {event_type} for telegram_id={telegram_id}")

    except Exception as e:
        logger.error(f"❌ Error logging event: {e}")


def get_active_otp(phone: str) -> Optional[Tuple[str, datetime]]:
    """
    Get active (non-expired, unverified) OTP for a phone.
    Returns (code, expires_at) or None
    Optimized: Single query with all conditions
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT code, expires_at
                FROM public.otp_codes
                WHERE phone = %s
                  AND verified = false
                  AND expires_at > NOW()
                ORDER BY created_at DESC
                LIMIT 1
            """, (phone,))

            result = cursor.fetchone()
            cursor.close()

            if result:
                return (result[0], result[1])
            return None

    except Exception as e:
        logger.error(f"❌ Error getting active OTP: {e}")
        return None


def save_otp_to_database(phone: str, code: str) -> bool:
    """
    Save OTP to database.
    Optimized: Single transaction with created_at
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Optimized: Delete old unverified OTPs in one query
            cursor.execute(
                "DELETE FROM public.otp_codes WHERE phone = %s AND verified = false",
                (phone,)
            )

            # Insert new OTP with created_at field
            expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
            created_at = datetime.utcnow()

            cursor.execute("""
                INSERT INTO public.otp_codes (phone, code, expires_at, verified, attempts, created_at)
                VALUES (%s, %s, %s, false, 0, %s)
            """, (phone, code, expires_at, created_at))

            conn.commit()
            cursor.close()
            logger.info(f"✅ OTP saved to database for {phone}, expires at {expires_at}, created at {created_at}")
            return True

    except Exception as e:
        logger.error(f"❌ Error saving OTP: {e}, type: {type(e).__name__}")
        return False


def escape_markdown(text: str) -> str:
    """Escape special Markdown characters in text"""
    logger.info(f"DEBUG escape_markdown: INPUT = {repr(text)}")
    if not text:
        logger.info("DEBUG escape_markdown: Empty text, returning empty")
        return ""
    # Escape special Markdown characters
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, '\\' + char)
    logger.info(f"DEBUG escape_markdown: OUTPUT = {repr(text)}")
    return text


def get_user_appointments(phone: str) -> List[Dict]:
    """Get user's upcoming appointments"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.id, a.start_time, a.end_time, a.status, u.name
                FROM public.appointments a
                JOIN public.users u ON a.user_id = u.id
                WHERE u.phone = %s AND a.start_time > NOW() AND a.status::text != 'cancelled'
                ORDER BY a.start_time ASC
                LIMIT 10
            """, (phone,))

            appointments = []
            for row in cursor.fetchall():
                appointments.append({
                    'id': row[0],
                    'start_time': row[1],
                    'end_time': row[2],
                    'status': row[3],
                    'user_name': row[4]
                })

            cursor.close()
            logger.info(f"📅 Retrieved {len(appointments)} appointments for {phone}")
            return appointments

    except Exception as e:
        logger.error(f"❌ Error getting appointments: {e}")
        return []


def cancel_appointment(appointment_id: int, phone: str) -> bool:
    """Cancel an appointment"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Verify appointment belongs to user and cancel it
            cursor.execute("""
                UPDATE public.appointments a
                SET status = 'cancelled'::appointmentstatus
                FROM public.users u
                WHERE a.id = %s
                  AND a.user_id = u.id
                  AND u.phone = %s
                  AND a.status::text != 'cancelled'
                RETURNING a.id
            """, (appointment_id, phone))

            result = cursor.fetchone()
            conn.commit()
            cursor.close()

            if result:
                logger.info(f"✅ Appointment {appointment_id} cancelled for {phone}")
                return True
            else:
                logger.warning(f"⚠️ Appointment {appointment_id} not found or already cancelled")
                return False

    except Exception as e:
        logger.error(f"❌ Error cancelling appointment: {e}")
        return False


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get main menu inline keyboard"""
    keyboard = [
        [InlineKeyboardButton("🔐 Отримати код", callback_data="get_otp")],
        [InlineKeyboardButton("📅 Мої записи", callback_data="appointments")],
        [InlineKeyboardButton("ℹ️ Статус коду", callback_data="status")],
        [
            InlineKeyboardButton("📱 Змінити номер", callback_data="reset"),
            InlineKeyboardButton("❓ Довідка", callback_data="help")
        ],
        [InlineKeyboardButton("🏥 Контакти клініки", callback_data="contacts")]
    ]
    return InlineKeyboardMarkup(keyboard)


def start_command(update: Update, context: CallbackContext) -> None:
    """Handle /start command"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "користувач"
    username = update.effective_user.username

    log_bot_event('start', user_id)
    logger.info(f"🚀 User {user_id} ({username}) started bot")

    phone = get_user_phone(user_id)
    if phone:
        # First, remove any existing reply keyboard
        update.message.reply_text(
            "🔄 Оновлення...",
            reply_markup=ReplyKeyboardRemove()
        )

        # Then show the menu with inline keyboard
        reply_markup = get_main_menu_keyboard()

        # Escape phone for MarkdownV2
        phone_escaped = phone.replace('+', '\\+')

        update.message.reply_text(
            f"👋 Привіт, {user_name}\\!\n\n"
            f"📱 Ваш номер: `{phone_escaped}`\n\n"
            f"Оберіть дію з меню 👇",
            parse_mode='MarkdownV2',
            reply_markup=reply_markup
        )
        logger.info(f"✅ Sent main menu to user {user_id} with phone {phone}")
    else:
        button = KeyboardButton("📱 Поділитися номером", request_contact=True)
        keyboard = [[button]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        update.message.reply_text(
            f"👋 Привіт, {user_name}!\n\n"
            "🏥 Я допомагаю отримувати коди для запису до лікаря.\n\n"
            "📝 Для початку поділіться номером телефону 👇\n\n"
            "або використайте команду:\n"
            "`/phone +380XXXXXXXXX`",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        logger.info(f"✅ Sent phone request to new user {user_id}")


def help_command(update: Update, context: CallbackContext) -> None:
    """Handle /help command"""
    user_id = update.effective_user.id
    log_bot_event('help', user_id)

    help_text = """
📖 *Довідка*

*Доступні команди:*
/start - Почати роботу з ботом
/help - Показати цю довідку
/phone - Вручну встановити номер телефону
/status - Перевірити активний код
/appointments - Переглянути мої записи
/reset - Змінити номер телефону

*Як користуватись:*
1️⃣ Поділіться номером телефону або `/phone +380ХХХХХХХХХ`
2️⃣ На сайті введіть ваш номер
3️⃣ Натисніть "🔐 Отримати код" в боті
4️⃣ Введіть код на сайті

*Важливо:*
• Код дійсний 5 хвилин
• Можна отримати макс. 3 коди на годину
• Скасувати запис можна через бота

❓ Проблеми? Напишіть адміністратору
"""

    update.message.reply_text(help_text, parse_mode='Markdown')
    logger.info(f"ℹ️ Help shown to user {user_id}")


def phone_command(update: Update, context: CallbackContext) -> None:
    """Command to set phone number manually (available for all users)"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    # Check if phone number was provided
    if not context.args or len(context.args) == 0:
        update.message.reply_text(
            "📱 *Команда /phone*\n\n"
            "Використання: `/phone +380501234567`\n\n"
            "Встановлює ваш номер телефону в боті.\n"
            "Можна використовувати замість кнопки 'Поділитися номером'.",
            parse_mode='Markdown'
        )
        return

    new_phone = context.args[0].strip()

    # Validate phone format
    if not new_phone.startswith('+'):
        update.message.reply_text(
            "❌ Невірний формат номера\n\n"
            "Номер повинен починатися з `+`\n"
            "Наприклад: `+380501234567`",
            parse_mode='Markdown'
        )
        return

    # Validate phone length (basic check)
    if len(new_phone) < 10 or len(new_phone) > 15:
        update.message.reply_text(
            "❌ Невірна довжина номера\n\n"
            "Номер повинен містити від 10 до 15 символів\n"
            "Наприклад: `+380501234567`",
            parse_mode='Markdown'
        )
        return

    # Save phone using existing function
    if save_user_phone(user_id, new_phone, username):
        # Show main menu after setting phone
        reply_markup = get_main_menu_keyboard()

        update.message.reply_text(
            f"✅ *Номер збережено*\n\n"
            f"📱 Ваш номер: `{new_phone}`\n\n"
            f"Тепер ви можете отримати код для входу на сайт 👇",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

        logger.info(f"✅ User {user_id} set phone to {new_phone}")
        log_bot_event('phone_command', user_id, new_phone, f"manual_phone_set")
    else:
        update.message.reply_text(
            "❌ Помилка збереження номера\n\n"
            "Спробуйте пізніше"
        )


def reset_command(update: Update, context: CallbackContext) -> None:
    """Handle /reset command - allow user to change phone"""
    user_id = update.effective_user.id
    log_bot_event('reset', user_id)

    button = KeyboardButton("📱 Поділитися номером", request_contact=True)
    keyboard = [[button]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    update.message.reply_text(
        "🔄 Зміна номера телефону\n\n"
        "Натисніть кнопку для вибору нового номера 👇",
        reply_markup=reply_markup
    )
    logger.info(f"🔄 User {user_id} requested phone reset")


def appointments_command(update: Update, context: CallbackContext) -> None:
    """Handle /appointments command - show user's appointments"""
    user_id = update.effective_user.id
    phone = get_user_phone(user_id)

    log_bot_event('appointments', user_id, phone)

    if not phone:
        update.message.reply_text(
            "❌ Спочатку поділіться номером телефону\n"
            "Використайте /start"
        )
        return

    appointments = get_user_appointments(phone)

    if not appointments:
        update.message.reply_text(
            "📅 *Мої записи*\n\n"
            "У вас немає майбутніх записів.\n\n"
            "💡 Запишіться на сайті!",
            parse_mode='Markdown'
        )
        return

    message = "📅 *Мої записи:*\n\n"

    for i, apt in enumerate(appointments, 1):
        start_time = apt['start_time']
        status_emoji = "✅" if apt['status'] == 'booked' else "📝"
        user_name = escape_markdown(apt['user_name'])

        message += (
            f"{status_emoji} *Запис #{i}*\n"
            f"📆 {start_time.strftime('%d.%m.%Y')}\n"
            f"🕐 {start_time.strftime('%H:%M')} - {apt['end_time'].strftime('%H:%M')}\n"
            f"👤 {user_name}\n"
            f"🆔 ID: `{apt['id']}`\n"
            f"━━━━━━━━━━━━━━\n\n"
        )

    message += "❌ Щоб скасувати запис, використайте:\n`/cancel ID_запису`"

    update.message.reply_text(message, parse_mode='Markdown')
    logger.info(f"📅 Appointments list shown to user {user_id}")


def cancel_command(update: Update, context: CallbackContext) -> None:
    """Handle /cancel command - cancel appointment"""
    user_id = update.effective_user.id
    phone = get_user_phone(user_id)

    if not phone:
        update.message.reply_text("❌ Спочатку поділіться номером телефону")
        return

    if not context.args:
        update.message.reply_text(
            "❌ Невірний формат\n\n"
            "Використання: `/cancel ID_запису`\n"
            "Приклад: `/cancel 123`\n\n"
            "Подивитись ID записів: /appointments",
            parse_mode='Markdown'
        )
        return

    try:
        appointment_id = int(context.args[0])
    except ValueError:
        update.message.reply_text("❌ ID запису має бути числом")
        return

    log_bot_event('cancel_appointment', user_id, phone, f"appointment_id={appointment_id}")

    if cancel_appointment(appointment_id, phone):
        update.message.reply_text(
            f"✅ Запис #{appointment_id} успішно скасовано!\n\n"
            f"💡 Можете записатись на інший час на сайті"
        )
        logger.info(f"✅ User {user_id} cancelled appointment {appointment_id}")
    else:
        update.message.reply_text(
            f"❌ Не вдалось скасувати запис #{appointment_id}\n\n"
            f"Можливі причини:\n"
            f"• Запис не існує\n"
            f"• Запис вже скасовано\n"
            f"• ID вказано невірно\n\n"
            f"Перевірте ID через /appointments"
        )
        logger.warning(f"⚠️ User {user_id} failed to cancel appointment {appointment_id}")


def handle_contact(update: Update, context: CallbackContext) -> None:
    """Handle phone number shared by user"""
    contact = update.message.contact
    user_id = update.effective_user.id
    username = update.effective_user.username

    if contact.user_id != user_id:
        update.message.reply_text(
            "❌ Будь ласка, поділіться ВАШИМ номером\n\n"
            "Натисніть кнопку ще раз"
        )
        logger.warning(f"⚠️ User {user_id} tried to share someone else's contact")
        return

    phone = contact.phone_number
    if not phone.startswith('+'):
        phone = '+' + phone

    # Save to database
    if save_user_phone(user_id, phone, username):
        log_bot_event('register', user_id, phone)

        # First remove the reply keyboard
        update.message.reply_text(
            "✅ Реєструю...",
            reply_markup=ReplyKeyboardRemove()
        )

        # Then show the main menu with inline keyboard
        reply_markup = get_main_menu_keyboard()

        update.message.reply_text(
            f"✅ Номер `{phone}` збережено!\n\n"
            f"📝 *Як користуватись:*\n"
            f"1️⃣ На сайті введіть: `{phone}`\n"
            f"2️⃣ Натисніть кнопку \"🔐 Отримати код\"\n"
            f"3️⃣ Отримаєте код\n"
            f"4️⃣ Введіть код на сайті\n\n"
            f"Оберіть дію з меню 👇",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        logger.info(f"📱 User {user_id} registered phone {phone}")
    else:
        update.message.reply_text(
            "❌ Помилка збереження номера\n\n"
            "Спробуйте пізніше або зверніться до адміністратора"
        )
        logger.error(f"❌ Failed to save phone for user {user_id}")


def handle_text(update: Update, context: CallbackContext) -> None:
    """Handle text messages - generate OTP or process registration"""
    user_id = update.effective_user.id

    logger.info(f"💬 Received text message from user {user_id}")

    # Check if user is in registration flow
    user_state = context.user_data.get('state')

    if user_state == STATE_WAITING_LAST_NAME or user_state == STATE_WAITING_FIRST_NAME:
        handle_name_input(update, context)
        return
    elif user_state == STATE_WAITING_BIRTHDATE:
        handle_birthdate_input(update, context)
        return

    # Normal OTP generation flow
    phone = get_user_phone(user_id)
    if not phone:
        logger.warning(f"⚠️ User {user_id} tried to get OTP without registered phone")
        button = KeyboardButton("📱 Поділитися номером", request_contact=True)
        keyboard = [[button]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        update.message.reply_text(
            "❌ Спочатку поділіться номером 👇\n\n"
            "Або використайте /start",
            reply_markup=reply_markup
        )
        return

    logger.info(f"🔐 User {user_id} ({phone}) requested OTP code")

    # Check rate limit
    is_allowed, count = check_rate_limit(phone)
    if not is_allowed:
        logger.warning(f"🚫 Rate limit exceeded for {phone}: {count}/{MAX_OTP_PER_HOUR}")
        reply_markup = get_main_menu_keyboard()
        update.message.reply_text(
            f"🚫 *Перевищено ліміт запитів*\n\n"
            f"Ви вже отримали {count} кодів за останню годину.\n"
            f"Максимум: {MAX_OTP_PER_HOUR} кодів/годину\n\n"
            f"⏰ Зачекайте до наступної години\n\n"
            f"Оберіть дію з меню 👇",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        log_bot_event('rate_limit_exceeded', user_id, phone, f"count={count}")
        return

    # Check if there's an active OTP that hasn't expired
    # Optimized: Use helper function instead of inline query
    active_otp = get_active_otp(phone)
    if active_otp:
        code, expires_at = active_otp
        remaining = (expires_at - datetime.utcnow()).total_seconds()
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)

        logger.info(f"⏳ User {phone} has active OTP: {code} (expires in {minutes}m {seconds}s)")
        update.message.reply_text(
            f"⏳ *У вас вже є активний код!*\n\n"
            f"🔐 Код: `{code}`\n"
            f"⏱ Дійсний ще *{minutes}хв {seconds}сек*\n\n"
            f"💡 Зачекайте, поки код не закінчиться",
            parse_mode='Markdown'
        )
        log_bot_event('active_otp_check', user_id, phone)
        return

    # Generate OTP
    code = ''.join([str(random.randint(0, 9)) for _ in range(OTP_LENGTH)])
    logger.info(f"🔢 Generated OTP code {code} for {phone}")

    # Save to database
    saved = save_otp_to_database(phone, code)

    if saved:
        logger.info(f"✅ OTP {code} saved and sent to user {user_id} ({phone})")
        reply_markup = get_main_menu_keyboard()
        update.message.reply_text(
            f"🔐 *Ваш код підтвердження:*\n\n"
            f"```\n"
            f"  {code}\n"
            f"```\n\n"
            f"📝 Введіть цей код на сайті\n"
            f"⏱ Дійсний {OTP_EXPIRY_MINUTES} хвилин\n\n"
            f"💡 Команда /status для перевірки коду\n\n"
            f"Оберіть дію з меню 👇",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        log_bot_event('otp_generated', user_id, phone, f"code={code}")

        # Check if user needs to complete profile
        if not check_user_profile_exists(phone):
            logger.info(f"📋 User {phone} needs to complete profile")
            context.user_data['phone'] = phone
            context.user_data['state'] = STATE_WAITING_LAST_NAME
            update.message.reply_text(
                "👤 *Для завершення реєстрації заповніть профіль*\n\n"
                "📝 Введіть ваше прізвище:",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
    else:
        logger.error(f"❌ Failed to save OTP for {phone}")
        reply_markup = get_main_menu_keyboard()
        update.message.reply_text(
            f"❌ *Помилка з'єднання з базою даних*\n\n"
            f"Спробуйте ще раз через хвилину\n\n"
            f"Якщо проблема повторюється, зверніться до адміністратора\n\n"
            f"Оберіть дію з меню 👇",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        log_bot_event('otp_failed', user_id, phone, 'database_error')


def handle_name_input(update: Update, context: CallbackContext) -> None:
    """Handle user last name and first name input during registration"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    state = context.user_data.get('state')

    # Handle last name input
    if state == STATE_WAITING_LAST_NAME:
        # Validate last name
        if len(text) < 2:
            update.message.reply_text(
                "❌ Прізвище повинно містити хоча б 2 символи.\n\n"
                "Спробуйте ще раз:"
            )
            return

        if len(text) > 50:
            update.message.reply_text(
                "❌ Прізвище надто довге (максимум 50 символів).\n\n"
                "Спробуйте ще раз:"
            )
            return

        # Allow only letters, spaces, hyphens, apostrophes, and Cyrillic
        import re
        if not re.match(r'^[a-zA-Zа-яА-ЯіІїЇєЄґҐ\s\-\']+$', text):
            update.message.reply_text(
                "❌ Прізвище може містити тільки літери, дефіси та апострофи.\n\n"
                "Спробуйте ще раз:"
            )
            return

        # Save last name and ask for first name
        context.user_data['last_name'] = text
        context.user_data['state'] = STATE_WAITING_FIRST_NAME

        update.message.reply_text(
            f"✅ Прийнято: {text}\n\n"
            "📝 Тепер введіть ваше ім'я:",
            parse_mode='Markdown'
        )
        logger.info(f"✅ User {user_id} provided last name: {text}")

    # Handle first name input
    elif state == STATE_WAITING_FIRST_NAME:
        # Validate first name
        if len(text) < 2:
            update.message.reply_text(
                "❌ Ім'я повинно містити хоча б 2 символи.\n\n"
                "Спробуйте ще раз:"
            )
            return

        if len(text) > 50:
            update.message.reply_text(
                "❌ Ім'я надто довге (максимум 50 символів).\n\n"
                "Спробуйте ще раз:"
            )
            return

        # Allow only letters, spaces, hyphens, apostrophes, and Cyrillic
        import re
        if not re.match(r'^[a-zA-Zа-яА-ЯіІїЇєЄґҐ\s\-\']+$', text):
            update.message.reply_text(
                "❌ Ім'я може містити тільки літери, дефіси та апострофи.\n\n"
                "Спробуйте ще раз:"
            )
            return

        # Save first name and ask for birthdate
        context.user_data['first_name'] = text
        context.user_data['state'] = STATE_WAITING_BIRTHDATE

        update.message.reply_text(
            f"✅ Прийнято: {text}\n\n"
            "📅 Тепер введіть вашу дату народження у форматі:\n"
            "`ДД.ММ.РРРР`\n\n"
            "Наприклад: `15.03.1990`",
            parse_mode='Markdown'
        )
        logger.info(f"✅ User {user_id} provided first name: {text}")


def handle_birthdate_input(update: Update, context: CallbackContext) -> None:
    """Handle user birthdate input during registration"""
    birthdate_str = update.message.text.strip()
    user_id = update.effective_user.id

    # Parse birthdate
    try:
        from datetime import date
        import re

        # Try to parse DD.MM.YYYY format
        match = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', birthdate_str)
        if not match:
            update.message.reply_text(
                "❌ Невірний формат дати.\n\n"
                "Використовуйте формат `ДД.ММ.РРРР`\n"
                "Наприклад: `15.03.1990`",
                parse_mode='Markdown'
            )
            return

        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        birthdate = date(year, month, day)

        # Validate birthdate
        if birthdate > date.today():
            update.message.reply_text(
                "❌ Дата народження не може бути в майбутньому.\n\n"
                "Спробуйте ще раз:"
            )
            return

        if birthdate < date(1900, 1, 1):
            update.message.reply_text(
                "❌ Невірна дата народження.\n\n"
                "Спробуйте ще раз:"
            )
            return

        # Save user profile
        phone = context.user_data.get('phone')
        last_name = context.user_data.get('last_name')
        first_name = context.user_data.get('first_name')

        if not phone or not last_name or not first_name:
            update.message.reply_text(
                "❌ Помилка: втрачено дані сесії.\n\n"
                "Почніть заново з команди /start"
            )
            context.user_data.clear()
            return

        # Combine last name and first name
        full_name = f"{last_name} {first_name}"

        # Save to database
        if save_user_profile(phone, full_name, birthdate.isoformat()):
            update.message.reply_text(
                "✅ *Профіль створено успішно!*\n\n"
                f"👤 Прізвище: {last_name}\n"
                f"👤 Ім'я: {first_name}\n"
                f"📅 Дата народження: {birthdate.strftime('%d.%m.%Y')}\n\n"
                "🎉 Тепер ви можете записатися на прийом через сайт!",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            log_bot_event('profile_created', user_id, phone, f"name={full_name}")
            logger.info(f"✅ Profile created for {phone}: {full_name}, {birthdate}")
        else:
            update.message.reply_text(
                "❌ Помилка при збереженні профілю.\n\n"
                "Спробуйте пізніше або зверніться до адміністратора."
            )
            logger.error(f"❌ Failed to save profile for {phone}")

        # Clear registration state
        context.user_data.clear()

    except ValueError as e:
        update.message.reply_text(
            "❌ Невірна дата.\n\n"
            "Використовуйте формат `ДД.ММ.РРРР`\n"
            "Наприклад: `15.03.1990`",
            parse_mode='Markdown'
        )
        logger.warning(f"⚠️ Invalid birthdate from user {user_id}: {birthdate_str}")
    except Exception as e:
        update.message.reply_text(
            "❌ Помилка обробки дати.\n\n"
            "Спробуйте ще раз:"
        )
        logger.error(f"❌ Error processing birthdate: {e}")


def status_command(update: Update, context: CallbackContext) -> None:
    """Show status"""
    user_id = update.effective_user.id
    phone = get_user_phone(user_id)

    log_bot_event('status', user_id, phone)

    if not phone:
        button = KeyboardButton("📱 Поділитися номером", request_contact=True)
        keyboard = [[button]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        update.message.reply_text(
            "❌ Номер не зареєстровано 👇",
            reply_markup=reply_markup
        )
        return

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Check for ANY active OTP (verified or not) that hasn't expired
            cursor.execute("""
                SELECT code, expires_at, verified FROM public.otp_codes
                WHERE phone = %s AND expires_at > %s
                ORDER BY id DESC LIMIT 1
            """, (phone, datetime.utcnow()))

            result = cursor.fetchone()
            cursor.close()

            if result:
                code, expires_at, verified = result
                remaining = (expires_at - datetime.utcnow()).total_seconds()
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)

                reply_markup = get_main_menu_keyboard()
                phone_escaped = phone.replace('+', '\\+')

                # Show different message for verified vs unverified codes
                status_icon = "✅" if verified else "⏳"
                status_text = "використаний" if verified else "активний"

                update.message.reply_text(
                    f"*Статус*\n\n"
                    f"Номер: `{phone_escaped}`\n"
                    f"Код: `{code}` {status_icon}\n"
                    f"Статус: {status_text}\n"
                    f"Дійсний ще *{minutes}хв {seconds}сек*\n\n"
                    f"Оберіть дію з меню 👇",
                    parse_mode='MarkdownV2',
                    reply_markup=reply_markup
                )
                logger.info(f"ℹ️ Status check for {phone}: code {code} ({status_text}, {minutes}m {seconds}s remaining)")
            else:
                reply_markup = get_main_menu_keyboard()
                phone_escaped = phone.replace('+', '\\+')

                update.message.reply_text(
                    f"*Статус*\n\n"
                    f"Номер: `{phone_escaped}`\n"
                    f"✅ Готовий до отримання нового коду\n\n"
                    f"Оберіть дію з меню 👇",
                    parse_mode='MarkdownV2',
                    reply_markup=reply_markup
                )
                logger.info(f"ℹ️ Status check for {phone}: no active code")
    except Exception as e:
        logger.error(f"❌ Status error: {e}")
        update.message.reply_text(
            "❌ Помилка перевірки статусу\n\n"
            "Спробуйте пізніше"
        )


def error_handler(update: Update, context: CallbackContext) -> None:
    """Handle errors with improved error messages and logging"""
    error = context.error
    error_type = type(error).__name__

    # Log detailed error information
    logger.error(
        f"❌ Error: {error_type}: {error}\n"
        f"Update: {update}\n"
        f"Traceback:",
        exc_info=error
    )

    # Log to database for analytics
    if update and update.effective_user:
        try:
            phone = get_user_phone(update.effective_user.id)
            log_bot_event(
                'error',
                update.effective_user.id,
                phone,
                f"{error_type}: {str(error)[:200]}"
            )
        except Exception as e:
            logger.error(f"Failed to log error event: {e}")

    # Send user-friendly error message
    if update and update.effective_message:
        try:
            # Customize message based on error type
            reply_markup = get_main_menu_keyboard()

            if "timeout" in str(error).lower() or "connection" in str(error).lower():
                message = (
                    "⏱ *Час очікування сплив*\n\n"
                    "Схоже, виникли проблеми з підключенням.\n"
                    "Спробуйте ще раз через кілька секунд.\n\n"
                    "Оберіть дію з меню 👇"
                )
            elif "database" in str(error).lower():
                message = (
                    "❌ *Помилка бази даних*\n\n"
                    "Спробуйте ще раз через хвилину.\n"
                    "Якщо проблема повторюється, зверніться до адміністратора.\n\n"
                    "Оберіть дію з меню 👇"
                )
            else:
                message = (
                    "❌ *Виникла помилка*\n\n"
                    "Спробуйте ще раз або зверніться до адміністратора.\n\n"
                    "Оберіть дію з меню 👇"
                )

            update.effective_message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")


def button_callback(update: Update, context: CallbackContext) -> None:
    """Handle inline button callbacks with comprehensive error handling"""
    try:
        query = update.callback_query
        user_id = query.from_user.id
        data = query.data

        # Answer callback query to remove loading state
        query.answer()

        logger.info(f"🔘 Button pressed: {data} by user {user_id}")

        # Route to appropriate handler based on callback data
        if data == "get_otp":
            # Simulate text message to trigger OTP generation
            phone = get_user_phone(user_id)
            if not phone:
                query.edit_message_text(
                    "❌ Спочатку поділіться номером телефону\n"
                    "Використайте /start"
                )
                return

            # Check rate limit
            is_allowed, count = check_rate_limit(phone)
            if not is_allowed:
                reply_markup = get_main_menu_keyboard()
                try:
                    query.edit_message_text(
                        f"🚫 *Перевищено ліміт запитів*\n\n"
                        f"Ви вже отримали {count} кодів за останню годину\\.\n"
                        f"Максимум: {MAX_OTP_PER_HOUR} кодів/годину\n\n"
                        f"⏰ Зачекайте до наступної години\n\n"
                        f"Оберіть дію з меню 👇",
                        parse_mode='MarkdownV2',
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    # Message already exists with same content, just answer callback
                    query.answer("🚫 Перевищено ліміт запитів")
                log_bot_event('rate_limit_exceeded', user_id, phone, f"count={count}")
                return

            # Check for active OTP
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT code, expires_at FROM public.otp_codes
                        WHERE phone = %s AND verified = false AND expires_at > %s
                        ORDER BY id DESC LIMIT 1
                    """, (phone, datetime.utcnow()))

                    result = cursor.fetchone()
                    cursor.close()

                    if result:
                        code, expires_at = result
                        remaining = (expires_at - datetime.utcnow()).total_seconds()
                        minutes = int(remaining // 60)
                        seconds = int(remaining % 60)

                        reply_markup = get_main_menu_keyboard()
                        query.edit_message_text(
                            f"⏳ *У вас вже є активний код!*\n\n"
                            f"🔐 Код: `{code}`\n"
                            f"⏱ Дійсний ще *{minutes}хв {seconds}сек*\n\n"
                            f"💡 Зачекайте, поки код не закінчиться",
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        return
            except Exception as e:
                logger.error(f"❌ Error checking existing OTP: {e}")
                # Continue to generate new code

            # Generate new OTP
            code = ''.join([str(random.randint(0, 9)) for _ in range(OTP_LENGTH)])
            saved = save_otp_to_database(phone, code)

            reply_markup = get_main_menu_keyboard()

            if saved:
                query.edit_message_text(
                    f"🔐 *Ваш код підтвердження:*\n\n"
                    f"```\n"
                    f"  {code}\n"
                    f"```\n\n"
                    f"📝 Введіть цей код на сайті\n"
                    f"⏱ Дійсний {OTP_EXPIRY_MINUTES} хвилин",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                log_bot_event('otp_generated', user_id, phone, f"code={code}")
            else:
                query.edit_message_text(
                    f"❌ *Помилка з'єднання з базою даних*\n\n"
                    f"Спробуйте ще раз через хвилину",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )

        elif data == "appointments":
            phone = get_user_phone(user_id)
            if not phone:
                query.edit_message_text("❌ Спочатку поділіться номером телефону")
                return

            logger.info(f"📋 Fetching appointments for user {user_id} ({phone})")
            appointments = get_user_appointments(phone)
            reply_markup = get_main_menu_keyboard()

            if not appointments:
                query.edit_message_text(
                    "📅 *Мої записи*\n\n"
                    "У вас немає майбутніх записів.\n\n"
                    "💡 Запишіться на сайті!",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                logger.info(f"✅ No appointments for user {user_id}")
                return

            logger.info(f"📅 Formatting {len(appointments)} appointments for user {user_id}")
            message = "📅 *Мої записи:*\n\n"
            for i, apt in enumerate(appointments[:5], 1):  # Show max 5
                start_time = apt['start_time']
                status_emoji = "✅" if apt['status'] == 'booked' else "📝"
                user_name = escape_markdown(apt['user_name'])

                # Format dates with escaped special chars for MarkdownV2
                date_str = start_time.strftime('%d.%m.%Y').replace('.', '\\.')
                time_str = f"{start_time.strftime('%H:%M')} \\- {apt['end_time'].strftime('%H:%M')}"

                message += (
                    f"{status_emoji} *Запис \\#{i}*\n"  # Escape # character
                    f"📆 {date_str}\n"
                    f"🕐 {time_str}\n"
                    f"👤 {user_name}\n"
                    f"━━━━━━━━━━━━━━\n\n"
                )

            message += "Для скасування: `/cancel ID\\_запису`"

            # Add cancel buttons for each appointment
            cancel_buttons = []
            for apt in appointments[:5]:
                cancel_buttons.append([
                    InlineKeyboardButton(
                        f"❌ Скасувати #{apt['id']}",
                        callback_data=f"cancel_{apt['id']}"
                    )
                ])
            cancel_buttons.append([InlineKeyboardButton("🔙 Головне меню", callback_data="main_menu")])
            reply_markup = InlineKeyboardMarkup(cancel_buttons)

            try:
                query.edit_message_text(message, parse_mode='MarkdownV2', reply_markup=reply_markup)
                logger.info(f"✅ Sent {len(appointments)} appointments to user {user_id}")
            except Exception as e:
                logger.error(f"❌ Error showing appointments to user {user_id}: {e}")
                query.answer("❌ Помилка відображення записів")

        elif data.startswith("cancel_"):
            appointment_id = int(data.split("_")[1])
            phone = get_user_phone(user_id)

            if cancel_appointment(appointment_id, phone):
                reply_markup = get_main_menu_keyboard()
                query.edit_message_text(
                    f"✅ Запис #{appointment_id} успішно скасовано!\n\n"
                    f"💡 Можете записатись на інший час на сайті",
                    reply_markup=reply_markup
                )
                log_bot_event('appointment_cancelled', user_id, phone, f"id={appointment_id}")
            else:
                reply_markup = get_main_menu_keyboard()
                query.edit_message_text(
                    f"❌ Не вдалось скасувати запис #{appointment_id}",
                    reply_markup=reply_markup
                )

        elif data == "status":
            phone = get_user_phone(user_id)
            if not phone:
                query.edit_message_text("❌ Спочатку поділіться номером телефону")
                return

            logger.info(f"📊 User {user_id} ({phone}) checking OTP status")

            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    # Check for ANY active OTP (verified or not) that hasn't expired
                    cursor.execute("""
                        SELECT code, expires_at, verified FROM public.otp_codes
                        WHERE phone = %s AND expires_at > %s
                        ORDER BY id DESC LIMIT 1
                    """, (phone, datetime.utcnow()))

                    result = cursor.fetchone()
                    cursor.close()

                    reply_markup = get_main_menu_keyboard()
                    phone_escaped = phone.replace('+', '\\+')

                    if result:
                        code, expires_at, verified = result
                        remaining = (expires_at - datetime.utcnow()).total_seconds()
                        minutes = int(remaining // 60)
                        seconds = int(remaining % 60)

                        # Show different message for verified vs unverified codes
                        status_icon = "✅" if verified else "⏳"
                        status_text = "використаний" if verified else "активний"

                        logger.info(f"✅ User {user_id} has code: {code} ({status_text}, {minutes}m {seconds}s remaining)")
                        query.edit_message_text(
                            f"*Статус*\n\n"
                            f"Номер: `{phone_escaped}`\n"
                            f"Код: `{code}` {status_icon}\n"
                            f"Статус: {status_text}\n"
                            f"Дійсний ще *{minutes}хв {seconds}сек*\n\n"
                            f"Оберіть дію з меню 👇",
                            parse_mode='MarkdownV2',
                            reply_markup=reply_markup
                        )
                    else:
                        logger.info(f"ℹ️ User {user_id} has no active code")
                        query.edit_message_text(
                            f"*Статус*\n\n"
                            f"Номер: `{phone_escaped}`\n"
                            f"✅ Готовий до отримання нового коду\n\n"
                            f"Оберіть дію з меню 👇",
                            parse_mode='MarkdownV2',
                            reply_markup=reply_markup
                        )
            except Exception as e:
                logger.error(f"❌ Status error for user {user_id}: {e}")
                query.answer("❌ Помилка перевірки статусу")

        elif data == "reset":
            button = KeyboardButton("📱 Поділитися номером", request_contact=True)
            keyboard = [[button]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

            # Send new message instead of editing (can't edit to show contact button)
            context.bot.send_message(
                chat_id=user_id,
                text="🔄 Зміна номера телефону\n\nНатисніть кнопку для вибору нового номера 👇",
                reply_markup=reply_markup
            )
            query.message.delete()

        elif data == "help":
            help_text = """
📖 *Довідка*

*Як користуватись:*
1️⃣ Поділіться номером телефону
2️⃣ На сайті введіть ваш номер
3️⃣ Натисніть "🔐 Отримати код"
4️⃣ Введіть код на сайті

*Важливо:*
• Код дійсний 5 хвилин
• Можна отримати макс. 3 коди на годину
• Скасувати запис можна тут

❓ Проблеми? Напишіть адміністратору
"""
            reply_markup = get_main_menu_keyboard()
            query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)

        elif data == "contacts":
            contacts_text = """
🏥 *Контакти клініки*

📍 *Адреса:*
вул. Медична, 123
Київ, 01001

📞 *Телефон:*
+380 50 123 4567

⏰ *Години роботи:*
Пн-Пт: 09:00 - 18:00
Сб: 10:00 - 15:00
Нд: вихідний

📧 *Email:*
info@clinic.com

💡 *Для запису:*
Використайте цей бот для отримання коду підтвердження та записуйтесь через веб-сайт клініки
"""
            reply_markup = get_main_menu_keyboard()
            query.edit_message_text(contacts_text, parse_mode='Markdown', reply_markup=reply_markup)

        elif data == "main_menu":
            phone = get_user_phone(user_id)
            reply_markup = get_main_menu_keyboard()
            query.edit_message_text(
                f"📱 Ваш номер: {phone}\n\n"
                f"Оберіть дію з меню 👇",
                reply_markup=reply_markup
            )

    except Exception as e:
        # Catch-all for any unhandled errors in button callback
        logger.error(f"❌ Unhandled error in button_callback: {e}", exc_info=True)
        try:
            query.answer("❌ Виникла помилка. Спробуйте ще раз.")
            query.edit_message_text(
                "❌ *Виникла помилка*\n\n"
                "Спробуйте ще раз або використайте /help",
                parse_mode='Markdown'
            )
        except Exception as notify_error:
            logger.error(f"Failed to notify user about error: {notify_error}")


def get_appointments_for_tomorrow() -> List[Dict]:
    """Get all appointments scheduled for tomorrow"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Calculate tomorrow's date range
            tomorrow = datetime.utcnow().date() + timedelta(days=1)
            tomorrow_start = datetime.combine(tomorrow, datetime.min.time())
            tomorrow_end = datetime.combine(tomorrow, datetime.max.time())

            cursor.execute("""
                SELECT
                    a.id,
                    a.start_time,
                    a.end_time,
                    u.phone,
                    u.name,
                    u.email,
                    a.notes
                FROM public.appointments a
                JOIN public.users u ON a.user_id = u.id
                WHERE a.start_time >= %s
                    AND a.start_time <= %s
                    AND a.status = 'booked'
                ORDER BY a.start_time
            """, (tomorrow_start, tomorrow_end))

            appointments = []
            for row in cursor.fetchall():
                appointments.append({
                    'id': row[0],
                    'start_time': row[1],
                    'end_time': row[2],
                    'phone': row[3],
                    'name': row[4],
                    'email': row[5],
                    'notes': row[6]
                })

            cursor.close()
            logger.info(f"📅 Found {len(appointments)} appointments for tomorrow")
            return appointments

    except Exception as e:
        logger.error(f"❌ Error fetching tomorrow's appointments: {e}")
        return []


def send_appointment_reminder(bot: Bot, phone: str, name: str, start_time: datetime, end_time: datetime, notes: Optional[str] = None) -> bool:
    """Send appointment reminder to user via Telegram"""
    try:
        # Get telegram_id for this phone number
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT telegram_id FROM public.telegram_users
                WHERE phone = %s
                ORDER BY last_active DESC
                LIMIT 1
            """, (phone,))

            result = cursor.fetchone()
            cursor.close()

            if not result:
                logger.info(f"⚠️ No Telegram account linked for {phone}")
                return False

            telegram_id = result[0]

        # Format reminder message
        start_str = start_time.strftime('%d.%m.%Y о %H:%M')
        end_str = end_time.strftime('%H:%M')
        safe_name = escape_markdown(name)
        safe_notes = escape_markdown(notes) if notes else None

        message = (
            f"🔔 *Нагадування про запис*\n\n"
            f"👤 {safe_name}\n"
            f"📅 Завтра, {start_str}\n"
            f"⏰ Тривалість: до {end_str}\n"
        )

        if safe_notes:
            message += f"\n📝 Примітки: {safe_notes}\n"

        message += (
            f"\n💡 Якщо ви не зможете прийти, будь ласка, скасуйте запис заздалегідь\n"
            f"📱 Використайте команду /appointments для перегляду записів"
        )

        # Send message
        bot.send_message(
            chat_id=telegram_id,
            text=message,
            parse_mode='Markdown'
        )

        logger.info(f"✅ Reminder sent to {phone} (telegram_id={telegram_id})")
        log_bot_event('reminder_sent', telegram_id, phone, f"appointment at {start_time}")
        return True

    except Exception as e:
        logger.error(f"❌ Error sending reminder to {phone}: {e}")
        return False


def send_cancellation_notification(bot: Bot, phone: str, name: str, start_time: datetime, cancelled_by: str = 'admin') -> bool:
    """Send cancellation notification to user via Telegram"""
    try:
        # Get telegram_id for this phone number
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT telegram_id FROM public.telegram_users
                WHERE phone = %s
                ORDER BY last_active DESC
                LIMIT 1
            """, (phone,))

            result = cursor.fetchone()
            cursor.close()

            if not result:
                logger.info(f"⚠️ No Telegram account linked for {phone}")
                return False

            telegram_id = result[0]

        # Format cancellation message
        start_str = start_time.strftime('%d.%m.%Y о %H:%M')
        safe_name = escape_markdown(name)

        message = (
            f"❌ *Запис скасовано*\n\n"
            f"👤 {safe_name}\n"
            f"📅 {start_str}\n\n"
        )

        if cancelled_by == 'admin':
            message += (
                f"⚠️ Ваш запис було скасовано лікарем\n"
                f"💡 Будь ласка, зателефонуйте в клініку для з'ясування деталей\n\n"
            )
        else:
            message += f"✅ Ваш запис успішно скасовано\n\n"

        message += f"📱 Використайте /start для створення нового запису"

        # Send message
        bot.send_message(
            chat_id=telegram_id,
            text=message,
            parse_mode='Markdown'
        )

        logger.info(f"✅ Cancellation notification sent to {phone} (telegram_id={telegram_id})")
        log_bot_event('cancellation_notification', telegram_id, phone, f"cancelled_by={cancelled_by}")
        return True

    except Exception as e:
        logger.error(f"❌ Error sending cancellation notification to {phone}: {e}")
        return False


def daily_reminder_job(bot: Bot):
    """Daily job to send appointment reminders at 12:00"""
    try:
        logger.info("⏰ Running daily reminder job...")
        appointments = get_appointments_for_tomorrow()

        success_count = 0
        fail_count = 0

        for appt in appointments:
            if send_appointment_reminder(
                bot=bot,
                phone=appt['phone'],
                name=appt['name'],
                start_time=appt['start_time'],
                end_time=appt['end_time'],
                notes=appt['notes']
            ):
                success_count += 1
            else:
                fail_count += 1

        logger.info(f"✅ Reminder job completed: {success_count} sent, {fail_count} failed")

    except Exception as e:
        logger.error(f"❌ Error in daily reminder job: {e}")


def process_pending_notifications(bot: Bot):
    """Process pending Telegram notifications from the database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get pending notifications
            cursor.execute("""
                SELECT id, phone, notification_type, message_data
                FROM public.telegram_notifications
                WHERE sent = false
                ORDER BY created_at
                LIMIT 50
            """)

            notifications = cursor.fetchall()

            if not notifications:
                return

            logger.info(f"📬 Processing {len(notifications)} pending notifications")

            for notif_id, phone, notif_type, message_data in notifications:
                try:
                    if notif_type == 'cancellation':
                        # Send cancellation notification
                        success = send_cancellation_notification(
                            bot=bot,
                            phone=phone,
                            name=message_data.get('name', 'Користувач'),
                            start_time=datetime.fromisoformat(message_data['start_time']),
                            cancelled_by=message_data.get('cancelled_by', 'admin')
                        )

                        if success:
                            # Mark as sent
                            cursor.execute("""
                                UPDATE public.telegram_notifications
                                SET sent = true, sent_at = NOW()
                                WHERE id = %s
                            """, (notif_id,))
                            conn.commit()
                            logger.info(f"✅ Notification {notif_id} sent successfully")
                        else:
                            logger.warning(f"⚠️ Failed to send notification {notif_id}")

                except Exception as e:
                    logger.error(f"❌ Error processing notification {notif_id}: {e}")
                    continue

            cursor.close()

    except Exception as e:
        logger.error(f"❌ Error in notification processor: {e}")


def main() -> None:
    """Main function"""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ No token!")
        return

    print("=" * 60)
    print("🤖 Telegram OTP Bot - Enhanced Version")
    print("=" * 60)

    # Initialize connection pool
    try:
        init_connection_pool(minconn=2, maxconn=10)
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return

    # Test database connection and initialize tables
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT current_database()')
            db_name = cursor.fetchone()[0]
            print(f"✅ Connected to database: {db_name}")
            cursor.close()

        # Initialize database tables
        print("📋 Initializing database tables...")
        if init_database_tables():
            print("✅ Database tables ready")
        else:
            print("⚠️  Warning: Some tables might not be created")

        # Check tables
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public' AND tablename IN ('otp_codes', 'telegram_users', 'appointments', 'bot_events')
                ORDER BY tablename
            """)
            tables = [row[0] for row in cursor.fetchall()]
            print(f"✅ Tables available: {tables}")
            cursor.close()

    except Exception as e:
        print(f"❌ Database check error: {e}")
        return

    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Initialize scheduler for daily reminders at 12:00
    # Use UTC timezone explicitly to avoid zoneinfo compatibility issues
    utc = pytz.UTC
    scheduler = BackgroundScheduler(timezone=utc)
    scheduler.add_job(
        daily_reminder_job,
        trigger=CronTrigger(hour=12, minute=0, timezone=utc),  # Every day at 12:00 UTC
        args=[updater.bot],
        id='daily_reminder',
        name='Daily Appointment Reminders',
        replace_existing=True
    )
    # Process pending notifications every 2 minutes
    scheduler.add_job(
        process_pending_notifications,
        trigger=CronTrigger(minute='*/2', timezone=utc),  # Every 2 minutes
        args=[updater.bot],
        id='notification_processor',
        name='Notification Processor',
        replace_existing=True
    )
    scheduler.start()
    logger.info("⏰ Scheduler started - reminders daily at 12:00 UTC, notifications every 2 min")

    # Command handlers
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("phone", phone_command))
    dp.add_handler(CommandHandler("status", status_command))
    dp.add_handler(CommandHandler("reset", reset_command))
    dp.add_handler(CommandHandler("appointments", appointments_command))
    dp.add_handler(CommandHandler("cancel", cancel_command))

    # Callback query handler for inline buttons
    dp.add_handler(CallbackQueryHandler(button_callback))

    # Message handlers
    dp.add_handler(MessageHandler(Filters.contact, handle_contact))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    # Error handler
    dp.add_error_handler(error_handler)

    print("✅ Bot started!")
    print("=" * 60)

    updater.start_polling(drop_pending_updates=True)
    updater.idle()


if __name__ == '__main__':
    main()
