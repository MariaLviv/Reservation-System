# Telegram OTP Bot - Medical Booking System

A production-ready Telegram bot for medical appointment booking system that handles OTP authentication, user registration, and appointment management.

## 📋 Table of Contents

- [🆕 Recent Updates (May 7, 2026)](#-recent-updates-may-7-2026)
- [System Overview](#system-overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Installation & Setup](#installation--setup)
- [Deployment](#deployment)
- [How It Works](#how-it-works)
- [Database Schema](#database-schema)
- [API Integration](#api-integration)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

---

## 🆕 Recent Updates (May 7, 2026)

### ✅ Admin Panel OTP Authentication (NEW)

#### Feature: Real OTP Verification for Admin Login
**Implementation**: Admin panel now uses real OTP authentication instead of simple phone matching.

**How it works**:
1. Admin phone number is stored in `backend/.env` file: `ADMIN_PHONE=+380501234599`
2. Frontend fetches admin phone from backend API: `GET /api/v1/admin/phone`
3. When admin enters correct phone, OTP is sent via Telegram bot
4. Admin receives 6-digit code in Telegram (@Toka_12_bot)
5. After successful OTP verification, admin gets session token

**Files Changed**:
- `backend/.env` - Admin phone configuration
- `backend/app/api/admin.py` - Added `GET /admin/phone` endpoint
- `frontend/src/services/adminService.js` - Added `getAdminPhone()` function
- `frontend/src/pages/AdminPage.js` - Full OTP flow implementation
- `frontend/src/styles/AdminPage.css` - OTP form styles

**Admin Login Flow**:
```
1. Admin enters phone number
   └─► Frontend validates against backend ADMIN_PHONE
        └─► If match: Send OTP via /admin/send-otp
             └─► Admin receives code in Telegram
                  └─► Admin enters code
                       └─► Verify via /admin/verify-otp
                            └─► Session token granted
```

**Configuration**:
```env
# In backend/.env
ADMIN_PHONE=+380501234599
```

**Status**: ✅ **IMPLEMENTED**

---

### ✅ Critical Fixes Implemented

#### 1. Markdown Parsing Error (FIXED)
**Issue**: `Can't parse entities: can't find end of the entity starting at byte offset 192`
- **Root Cause**: Unescaped underscore character in static text `"ID_запису"`
- **Fix Applied**: Line 1313 - Changed to `"ID\_запису"` with escaped underscore
- **Status**: ✅ **RESOLVED** - Appointments now display without errors
- **Affected Function**: `button_callback()` - appointments display

#### 2. PostgreSQL Enum Casting Error (FIXED)
**Issue**: `invalid input value for enum appointmentstatus: "cancelled"`
- **Root Cause**: Direct string comparison with PostgreSQL enum type
- **Fix Applied**: 
  - Line 412: `a.status::text != 'cancelled'` (cast enum to text for comparison)
  - Line 445: `status = 'cancelled'::appointmentstatus` (cast string to enum for assignment)
- **Status**: ✅ **RESOLVED** - Enum operations work correctly

#### 3. Missing Database Table (FIXED)
**Issue**: `relation "telegram_notifications" does not exist`
- **Root Cause**: Table not created in initial database setup
- **Fix Applied**: Lines 183-194 - Added `telegram_notifications` table creation
- **Table Schema**:
  ```sql
  CREATE TABLE IF NOT EXISTS public.telegram_notifications (
      id SERIAL PRIMARY KEY,
      phone VARCHAR(20) NOT NULL,
      notification_type VARCHAR(50) NOT NULL,
      message_data JSONB,
      sent BOOLEAN DEFAULT FALSE,
      created_at TIMESTAMP DEFAULT NOW(),
      sent_at TIMESTAMP
  )
  ```
- **Status**: ✅ **RESOLVED** - Notification system fully functional

#### 4. Invalid URL in Inline Keyboard (FIXED)
**Issue**: `Inline keyboard button url 'http://localhost:3000' is invalid: wrong http url`
- **Root Cause**: Telegram API doesn't accept localhost URLs
- **Fix Applied**: Removed booking website button from inline keyboard
- **Note**: Users access booking site through browser directly
- **Status**: ✅ **RESOLVED** - No more URL validation errors

### 🆕 New Features Added

#### 1. Auto-Recovery Error Handler
**Feature**: Bot automatically shows main menu after any error
- **Implementation**: Updated `error_handler()` function (lines 1130-1184)
- **Behavior**: When error occurs:
  1. Logs detailed error information
  2. Automatically displays main menu to user
  3. Allows user to continue without typing `/start`
- **Benefits**: Improved user experience, no dead-ends
- **Status**: ✅ **IMPLEMENTED**

#### 2. Smart Text Message Handling
**Feature**: Any text input shows main menu instead of trying to generate OTP
- **Implementation**: Modified `handle_text()` function (line 770)
- **Previous Behavior**: Text messages triggered OTP generation flow
- **New Behavior**: Any text message displays main menu with phone number and action buttons
- **Benefits**: Cleaner UX, no confusion for users
- **Status**: ✅ **IMPLEMENTED**

#### 3. Markdown Special Character Escaping
**Feature**: Automatic escaping of Markdown special characters in user data
- **Implementation**: New `escape_markdown()` function (lines 389-400)
- **Characters Handled**: `_ * [ ] ( ) ~ ` > # + - = | { } . !`
- **Applied To**: User names, appointment details, notes
- **Benefits**: Prevents Markdown parsing errors with user-generated content
- **Status**: ✅ **IMPLEMENTED**

### 📊 Testing & Verification

All fixes have been tested and verified on Replit production environment:

```
✅ Bot starts successfully
✅ Database tables created (4 tables: appointments, bot_events, otp_codes, telegram_users)
✅ OTP generation works
✅ Appointments display without errors
✅ Inline buttons functional
✅ Error recovery working
✅ Text messages show main menu
✅ Scheduler running (reminders + notifications)
```

### 🔧 Technical Improvements

- **Enhanced Logging**: Added debug logs for Markdown character detection
- **Connection Pool Health**: Improved connection validation before queries
- **Error Tracking**: Comprehensive error logging to `bot_events` table
- **Database Indexes**: Optimized queries with proper indexing
- **Code Quality**: Fixed enum handling across all SQL queries

### 📝 Deployment Notes

**Current Version**: 2.0.0  
**Status**: ✅ Production Ready  
**Last Tested**: May 7, 2026  
**Platform**: Replit (with Supabase PostgreSQL)  

**Deployment Checklist**:
- ✅ All critical bugs fixed
- ✅ Markdown errors resolved
- ✅ Database tables created
- ✅ Error handling improved
- ✅ User experience enhanced
- ✅ Comprehensive logging added

---

## 🎯 System Overview

This Telegram bot is part of a medical appointment booking system that provides:
- **OTP Authentication**: Secure phone number verification via Telegram
- **User Registration**: Collect user profile (name, birthdate) on first use
- **Appointment Management**: View and cancel appointments
- **Database Persistence**: PostgreSQL (Supabase) for all data
- **Connection Pooling**: Efficient database connections
- **Rate Limiting**: Prevent OTP spam (3 codes/hour max)

### Key Benefits

✅ **Faster than SMS** - Instant delivery  
✅ **Free** - No SMS gateway costs  
✅ **User-friendly** - Interactive buttons  
✅ **Persistent** - Database-backed state  
✅ **Scalable** - Connection pooling & caching  

---

## 🏗️ Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER FLOW                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────┐    ┌──────────────┐    ┌──────────────────┐
│   Web Frontend  │◄──►│   Backend    │◄──►│  Telegram Bot    │
│   (React SPA)   │    │  (FastAPI)   │    │ (python-telegram)│
└─────────────────┘    └──────────────┘    └──────────────────┘
         │                     │                      │
         │                     │                      │
         │              ┌──────▼──────┐              │
         │              │  PostgreSQL  │◄─────────────┘
         │              │  (Supabase)  │
         │              └──────────────┘
         │                     │
         └─────────────────────┘
```

### Component Interaction Flow

```
┌─────────┐                                           ┌──────────┐
│  User   │                                           │ Telegram │
│ Browser │                                           │   Bot    │
└────┬────┘                                           └────┬─────┘
     │                                                      │
     │ 1. Enter phone: +380501234567                       │
     │─────────────────────────►┌─────────┐               │
     │                           │ Backend │               │
     │                           └────┬────┘               │
     │                                │                    │
     │                    2. Get OTP code from bot         │
     │                                ├───────────────────►│
     │                                │                    │
     │                                │   3. Generate OTP  │
     │                                │      573074        │
     │                                │◄───────────────────┤
     │                                │                    │
     │                    4. Save to database              │
     │                                │                    │
     │                           ┌────▼────┐               │
     │                           │Database │               │
     │                           └────┬────┘               │
     │                                │                    │
     │                                │   5. Send code     │
     │◄────────────────────────────────────────────────────┤
     │     "Your OTP: 573074"                              │
     │                                                     │
     │ 6. Enter code on website                            │
     │─────────────────────────►┌─────────┐               │
     │                           │ Backend │               │
     │                           └────┬────┘               │
     │                                │                    │
     │                    7. Verify code                   │
     │                           ┌────▼────┐               │
     │                           │Database │               │
     │                           └────┬────┘               │
     │                                │                    │
     │ 8. Access granted              │                    │
     │◄───────────────────────────────┤                    │
     │                                                     │
```

### Database Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SUPABASE POSTGRESQL                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐        ┌──────────────────┐          │
│  │  telegram_users  │        │    otp_codes     │          │
│  ├──────────────────┤        ├──────────────────┤          │
│  │ id (PK)          │        │ id (PK)          │          │
│  │ telegram_id (UQ) │        │ phone            │          │
│  │ phone            │        │ code             │          │
│  │ username         │        │ expires_at       │          │
│  │ registered_at    │        │ verified         │          │
│  │ last_active      │        │ attempts         │          │
│  └──────────────────┘        │ created_at       │          │
│                              └──────────────────┘          │
│                                                              │
│  ┌──────────────────┐        ┌──────────────────┐          │
│  │      users       │        │  appointments    │          │
│  ├──────────────────┤        ├──────────────────┤          │
│  │ id (PK)          │◄───┐   │ id (PK)          │          │
│  │ phone (UQ)       │    └───│ user_id (FK)     │          │
│  │ name             │        │ start_time       │          │
│  │ birthdate        │        │ end_time         │          │
│  │ email            │        │ status           │          │
│  │ is_blacklisted   │        │ notes            │          │
│  │ created_at       │        │ created_at       │          │
│  └──────────────────┘        └──────────────────┘          │
│                                                              │
│  ┌──────────────────┐                                       │
│  │   bot_events     │                                       │
│  ├──────────────────┤                                       │
│  │ id (PK)          │                                       │
│  │ event_type       │                                       │
│  │ telegram_id      │                                       │
│  │ phone            │                                       │
│  │ details          │                                       │
│  │ created_at       │                                       │
│  └──────────────────┘                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

### Core Features

1. **OTP Authentication**
   - Generate 6-digit OTP codes
   - 5-minute expiration
   - Rate limiting (3 codes/hour)
   - Auto-cleanup of expired codes

2. **User Registration**
   - First-time user flow
   - Collect name and birthdate
   - Form validation
   - Profile persistence

3. **Appointment Management**
   - View upcoming appointments
   - Cancel appointments
   - Appointment notifications

4. **Interactive Interface**
   - Inline keyboard buttons
   - One-tap actions
   - User-friendly messages
   - Ukrainian language support

### Technical Features

- **Database Persistence**: All state in PostgreSQL
- **Connection Pooling**: SimpleConnectionPool (2-10 connections)
- **Error Handling**: Comprehensive try-catch with logging
- **Rate Limiting**: Database-tracked request counts
- **Analytics**: Event logging for monitoring
- **Auto Table Creation**: Database schema auto-initialization

---

## 🛠️ Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Language** | Python | 3.10+ |
| **Bot Framework** | python-telegram-bot | 13.15 |
| **Database** | PostgreSQL (Supabase) | Latest |
| **DB Driver** | psycopg2-binary | Latest |
| **Environment** | python-dotenv | Latest |
| **Deployment** | Replit | N/A |

---

## 📁 Project Structure

```
telegram_bot/
├── bot.py                    # Main bot application
├── .env                      # Environment variables (local only)
├── requirements.txt          # Python dependencies
└── README.md                # This file

Key Components in bot.py:
├── Constants                 # Configuration (OTP_LENGTH, expiry, etc.)
├── Database Functions
│   ├── init_connection_pool()        # Setup connection pool
│   ├── get_db_connection()           # Context manager for connections
│   ├── init_database_tables()        # Create tables if not exist
│   ├── save_user_phone()             # Store telegram user
│   ├── get_user_phone()              # Retrieve user phone
│   ├── check_user_profile_exists()   # Check if profile complete
│   ├── save_user_profile()           # Store user profile
│   ├── check_rate_limit()            # Validate request rate
│   ├── save_otp_to_database()        # Store OTP code
│   ├── log_bot_event()               # Analytics logging
│   ├── get_user_appointments()       # Fetch appointments
│   └── cancel_appointment()          # Cancel booking
├── Command Handlers
│   ├── start_command()               # /start command
│   ├── status_command()              # /status command
│   ├── help_command()                # /help command
│   ├── reset_command()               # /reset command
│   ├── appointments_command()        # /appointments command
│   └── handle_contact()              # Phone sharing
├── Message Handlers
│   ├── handle_text()                 # Text input router
│   ├── handle_name_input()           # Registration: name
│   └── handle_birthdate_input()      # Registration: birthdate
├── Button Handlers
│   ├── button_callback()             # Inline button handler
│   ├── get_main_menu_keyboard()      # Main menu buttons
│   └── handle_cancel_appointment()   # Cancel appointment flow
└── Main Function
    └── main()                        # Bot initialization & startup
```

---

## 🚀 Installation & Setup

### Prerequisites

- Python 3.10 or higher
- PostgreSQL database (Supabase account)
- Telegram Bot Token (from @BotFather)

### Local Development Setup

1. **Clone the repository**
```bash
cd /path/to/telegram_bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

Create `.env` file:
```env
TELEGRAM_BOT_TOKEN=6213735016:AAGVhHj-oV2mfJfGgddACFRTFg-IoDFuq10
DATABASE_URL=postgresql://user:password@host:port/database
OTP_LENGTH=6
OTP_EXPIRY_MINUTES=5
MAX_OTP_PER_HOUR=3
```

4. **Run the bot**
```bash
python bot.py
```

You should see:
```
✅ Using Supabase database (matches backend)
✅ Connection pool initialized (min=2, max=10)
✅ Connected to database: postgres
📋 Initializing database tables...
✅ Database tables initialized successfully
✅ Tables available: ['telegram_users', 'otp_codes', 'bot_events', 'appointments', 'users']
✅ Bot started!
```

---

## 🌐 Deployment

### Deploy to Replit (Recommended)

#### Step 1: Create Replit Project

1. Go to [replit.com](https://replit.com)
2. Click **"Create Repl"**
3. Select **"Python"** template
4. Name: `telegram-otp-bot`

#### Step 2: Upload Files

Upload these files to Replit:
- `bot.py`
- `requirements.txt`

#### Step 3: Configure Secrets

⚠️ **IMPORTANT**: Replit uses Secrets, not `.env` files

Click 🔒 **Secrets** (left sidebar) and add:

```
TELEGRAM_BOT_TOKEN = 6213735016:AAGVhHj-oV2mfJfGgddACFRTFg-IoDFuq10
```

Note: Database URL is hardcoded in `bot.py` line 51 to ensure correct database connection.

#### Step 4: Configure Run Command

Create `.replit` file:
```toml
run = "python bot.py"
language = "python3"

[nix]
channel = "stable-22_11"

[deployment]
run = ["python", "bot.py"]
```

#### Step 5: Start Bot

Click **"Run"** button. Monitor console output for:
```
✅ Using Supabase database (matches backend)
✅ Bot started!
```

#### Step 6: Keep Bot Running 24/7

1. Click **"Always On"** in Replit settings (requires paid plan)
2. Bot will auto-restart on crashes
3. Handles automatic deployments

### Alternative: Deploy to Heroku

1. **Create `Procfile`**
```
worker: python bot.py
```

2. **Deploy**
```bash
heroku create your-bot-name
git push heroku main
heroku ps:scale worker=1
```

### Alternative: Deploy to VPS

1. **Setup systemd service**

Create `/etc/systemd/system/telegram-bot.service`:
```ini
[Unit]
Description=Telegram OTP Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/telegram_bot
ExecStart=/usr/bin/python3 /path/to/telegram_bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

2. **Start service**
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

---

## ⚙️ How It Works

### User Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                       FIRST TIME USER                             │
└──────────────────────────────────────────────────────────────────┘

1. User starts bot
   └─► /start command
        └─► Bot asks to share phone number
             └─► User clicks "📱 Поділитися номером"
                  └─► Bot saves telegram_id + phone

2. User requests OTP from website
   └─► Website: "Enter phone: +380501234567"
        └─► Bot generates OTP: 573074
             └─► Saves to database (expires in 5 min)
                  └─► Sends to user via Telegram

3. Check if user has profile
   └─► Query: SELECT * FROM users WHERE phone = '+380501234567'
        └─► NOT FOUND
             └─► Bot asks: "📝 Введіть ваше ім'я та прізвище:"
                  └─► User enters: "Іван Петренко"
                       └─► STATE = waiting_birthdate
                            └─► Bot asks: "📅 Введіть дату народження (ДД.ММ.РРРР):"
                                 └─► User enters: "15.03.1990"
                                      └─► Validates & saves profile
                                           └─► "✅ Профіль створено успішно!"

4. User enters OTP on website
   └─► Website verifies code
        └─► Login successful!

┌──────────────────────────────────────────────────────────────────┐
│                      RETURNING USER                               │
└──────────────────────────────────────────────────────────────────┘

1. User requests OTP from website
   └─► Bot generates & sends OTP
        └─► Profile exists → No registration flow
             └─► User enters code
                  └─► Login successful!

2. User checks appointments
   └─► Clicks "📅 Мої записи" button
        └─► Bot queries appointments table
             └─► Shows list of upcoming appointments
                  └─► User can cancel if needed
```

### OTP Generation Flow

```python
def handle_text(update, context):
    """
    OTP Generation Logic
    
    1. Get user's phone from database
    2. Check rate limit (max 3 codes/hour)
    3. Check for active unexpired code
    4. Generate new 6-digit code
    5. Save to database with expiration
    6. Send to user
    7. Check if profile exists
       └─► If NOT exists: Start registration flow
       └─► If exists: Done
    """
```

### User Registration State Machine

```
┌─────────────┐
│  NO STATE   │ Initial state
└──────┬──────┘
       │
       │ OTP sent & profile missing
       ▼
┌─────────────┐
│waiting_name │ Waiting for user's name
└──────┬──────┘
       │
       │ Valid name entered
       ▼
┌──────────────────┐
│waiting_birthdate │ Waiting for birthdate
└────────┬─────────┘
         │
         │ Valid birthdate entered
         ▼
    ┌─────────┐
    │  DONE   │ Profile saved
    └─────────┘
```

### Button Interaction Flow

```
User clicks button → CallbackQueryHandler
                          │
                          ▼
                 button_callback(query)
                          │
                          ▼
              Check callback_data value
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
  "get_otp"        "appointments"      "status"
  Generate OTP     Show bookings       Show OTP status
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                          ▼
              Answer callback query
                          │
                          ▼
                Send response message
```

---

## 🗄️ Database Schema

### Table: `telegram_users`

Stores Telegram user data and phone mapping.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| telegram_id | BIGINT | UNIQUE, NOT NULL | Telegram user ID |
| phone | VARCHAR(20) | NOT NULL | Phone number |
| username | VARCHAR(255) | | Telegram username |
| registered_at | TIMESTAMP | DEFAULT NOW() | Registration time |
| last_active | TIMESTAMP | DEFAULT NOW() | Last activity |

**Indexes:**
- `idx_telegram_users_telegram_id` on `telegram_id`

### Table: `otp_codes`

Stores OTP codes with expiration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| phone | VARCHAR(20) | NOT NULL | Phone number |
| code | VARCHAR(10) | NOT NULL | OTP code |
| expires_at | TIMESTAMP | NOT NULL | Expiration time |
| verified | BOOLEAN | DEFAULT FALSE | Verification status |
| attempts | INTEGER | DEFAULT 0 | Verification attempts |
| created_at | TIMESTAMP | DEFAULT NOW() | Creation time |

**Indexes:**
- `idx_otp_phone` on `phone`
- `idx_otp_expires` on `expires_at`

### Table: `users`

Main user profiles (created by backend, used by bot).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| phone | VARCHAR(20) | UNIQUE, NOT NULL | Phone number |
| name | VARCHAR(255) | NOT NULL | Full name |
| birthdate | DATE | NOT NULL | Date of birth |
| email | VARCHAR(255) | | Email address |
| is_blacklisted | BOOLEAN | DEFAULT FALSE | Blacklist status |
| email_verified | BOOLEAN | DEFAULT FALSE | Email verification |
| notes | TEXT | | Admin notes |
| created_at | TIMESTAMP | DEFAULT NOW() | Registration time |

### Table: `appointments`

User appointments (created by backend, queried by bot).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| user_id | INTEGER | FOREIGN KEY (users.id) | User reference |
| start_time | TIMESTAMP | NOT NULL | Appointment start |
| end_time | TIMESTAMP | NOT NULL | Appointment end |
| status | ENUM | NOT NULL | 'booked' or 'cancelled' |
| notes | TEXT | | Appointment notes |
| created_at | TIMESTAMP | DEFAULT NOW() | Booking time |

### Table: `bot_events`

Analytics and logging.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| event_type | VARCHAR(50) | NOT NULL | Event type |
| telegram_id | BIGINT | NOT NULL | Telegram user ID |
| phone | VARCHAR(20) | | Phone number |
| details | TEXT | | Event details |
| created_at | TIMESTAMP | DEFAULT NOW() | Event time |

---

## 🔌 API Integration

### Backend Configuration

The bot expects the backend to use the **same database** (Supabase).

#### Database URL

Both backend and bot must connect to:
```
postgresql://postgres.wgexfdydnmspnpssvdsq:reservationDBword_12@aws-0-eu-west-1.pooler.supabase.com:6543/postgres
```

⚠️ **Critical**: If database URLs don't match, OTP verification will fail!

### How Bot & Backend Communicate

```
┌──────────┐                  ┌──────────┐
│   Bot    │                  │ Backend  │
└────┬─────┘                  └────┬─────┘
     │                             │
     │ 1. Generates OTP             │
     │                             │
     │ 2. INSERT INTO otp_codes     │
     │    (phone, code, expires)    │
     └────────►┌──────────┐◄────────┘
               │ Database │
               └──────────┘
                    │
     ┌──────────────┘
     │
     │ 3. User enters code on website
     │
     └────────►┌──────────┐
               │ Backend  │
               └────┬─────┘
                    │
     4. SELECT * FROM otp_codes
        WHERE phone = ... AND code = ...
                    │
               ┌────▼─────┐
               │ Database │
               └──────────┘
```

**No direct API calls between bot and backend!**  
All communication happens through shared database.

---

## 🔒 Security

### Security Measures

1. **Rate Limiting**
   - Maximum 3 OTP codes per hour per phone
   - Tracked in database
   - Prevents spam attacks

2. **OTP Expiration**
   - Codes valid for 5 minutes only
   - Auto-cleanup of expired codes
   - One-time use enforced

3. **Input Validation**
   - Phone format: `+380XXXXXXXXX`
   - Name: 2-100 characters, letters only
   - Birthdate: DD.MM.YYYY format, not in future

4. **Database Security**
   - Connection pooling
   - Parameterized queries (SQL injection prevention)
   - SSL connections to Supabase

5. **Error Handling**
   - No sensitive data in error messages
   - Comprehensive logging
   - Graceful degradation

### Best Practices

✅ **DO:**
- Use environment variables for tokens
- Enable SSL for database connections
- Log all authentication attempts
- Validate all user inputs
- Use connection pooling

❌ **DON'T:**
- Store tokens in code
- Share database credentials
- Log sensitive user data
- Allow unlimited OTP requests
- Use plain text for passwords

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Bot doesn't respond

**Symptoms:**
- No response to `/start`
- Commands ignored

**Solutions:**
```bash
# Check bot is running
ps aux | grep bot.py

# Check logs
tail -f /var/log/telegram-bot.log  # VPS
# OR check Replit console

# Verify token
echo $TELEGRAM_BOT_TOKEN

# Test bot token
curl https://api.telegram.org/bot<TOKEN>/getMe
```

#### 2. Database connection errors

**Symptoms:**
```
❌ Failed to initialize connection pool
⚠️ WARNING: Using heliumdb - OTP verification will FAIL!
```

**Solutions:**
1. Verify database URL in `bot.py` line 51
2. Should contain: `supabase.com`
3. Test connection:
```python
import psycopg2
conn = psycopg2.connect(DATABASE_URL)
print("✅ Connected!")
```

#### 3. OTP not working

**Symptoms:**
- User enters code on website
- "Invalid code" error

**Solutions:**
1. Check database URL matches between bot and backend
2. Verify code in database:
```sql
SELECT * FROM otp_codes 
WHERE phone = '+380501234567' 
ORDER BY created_at DESC 
LIMIT 1;
```
3. Check expiration: `expires_at > NOW()`
4. Check `verified = false`

#### 4. Registration form not appearing

**Symptoms:**
- OTP sent but no profile form

**Solutions:**
1. Check if profile already exists:
```sql
SELECT * FROM users WHERE phone = '+380501234567';
```
2. Test profile check:
```python
exists = check_user_profile_exists('+380501234567')
print(f"Profile exists: {exists}")
```

#### 5. Rate limit issues

**Symptoms:**
```
🚫 Перевищено ліміт запитів
```

**Solutions:**
1. Check OTP count:
```sql
SELECT COUNT(*) FROM otp_codes 
WHERE phone = '+380501234567' 
AND created_at > NOW() - INTERVAL '1 hour';
```
2. Increase limit in bot.py:
```python
MAX_OTP_PER_HOUR = 5  # Increase from 3
```

### Debug Mode

Enable debug logging:

```python
# In bot.py, change:
logging.basicConfig(
    level=logging.DEBUG  # Changed from INFO
)
```

This will show:
- All database queries
- User state transitions
- Button clicks
- Error stack traces

### Health Check

Test bot health:

```bash
# Check database connection
python -c "from bot import init_connection_pool, get_db_connection; init_connection_pool(); 
with get_db_connection() as conn: print('✅ DB Connected')"

# Check tables exist
python -c "from bot import init_database_tables; init_database_tables()"

# Test OTP generation
python -c "from bot import check_rate_limit; print(check_rate_limit('+380501234567'))"
```

---

## 📊 Monitoring & Analytics

### Event Logging

All events are logged to `bot_events` table:

```sql
-- Most active users
SELECT phone, COUNT(*) as event_count
FROM bot_events
GROUP BY phone
ORDER BY event_count DESC
LIMIT 10;

-- OTP generation stats
SELECT 
    DATE(created_at) as date,
    COUNT(*) as otp_count
FROM bot_events
WHERE event_type = 'otp_generated'
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- Failed attempts
SELECT * FROM bot_events
WHERE event_type LIKE '%failed%'
ORDER BY created_at DESC
LIMIT 20;
```

### Performance Metrics

Monitor key metrics:

```sql
-- Average OTP verification time
WITH otp_times AS (
    SELECT 
        phone,
        code,
        created_at,
        (SELECT created_at FROM bot_events 
         WHERE event_type = 'otp_verified' 
         AND phone = otp_codes.phone 
         AND created_at > otp_codes.created_at
         LIMIT 1) as verified_at
    FROM otp_codes
    WHERE verified = true
)
SELECT AVG(verified_at - created_at) as avg_verification_time
FROM otp_times;

-- Registration completion rate
SELECT 
    (SELECT COUNT(*) FROM telegram_users) as total_users,
    (SELECT COUNT(*) FROM users) as completed_profiles,
    ROUND(100.0 * (SELECT COUNT(*) FROM users) / (SELECT COUNT(*) FROM telegram_users), 2) as completion_rate;
```

---