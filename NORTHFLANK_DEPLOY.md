# Northflank Deployment Guide

## Your Setup

| Component | Platform |
|-----------|----------|
| Frontend | Vercel / Cloudflare Pages |
| Backend (FastAPI) | **Northflank** (Service 1) |
| Telegram Bot | **Northflank** (Service 2) |
| Database | **Supabase** (external) |
| Redis | Disabled or **Upstash** (external) |

---

## Free Tier Limits

- 2 services ✅ (Backend + Bot)
- 0.1 vCPU per service
- 256 MB RAM per service
- 1 addon (not needed - using Supabase)

---

## Step 1: Create Northflank Account

1. Go to https://northflank.com
2. Sign up with GitHub
3. Create a new **Project**

---

## Step 2: Deploy Backend

### 2.1 Create Service

1. **Add Service → Combined Service**
2. **Name:** `backend`
3. **Repository:** Connect your GitHub repo
4. **Branch:** `main`
5. **Build:**
   - Context: `/backend`
   - Dockerfile: `Dockerfile.northflank`

### 2.2 Set Environment Variables

Add these in **Environment** tab:

```
DATABASE_URL=postgresql://postgres.[PROJECT]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
SECRET_KEY=your-secret-key-generate-random
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$2b$12$your_bcrypt_hash
ADMIN_PHONE=+380501234567
CORS_ORIGINS=https://your-frontend.vercel.app
FRONTEND_URL=https://your-frontend.vercel.app
REDIS_ENABLED=false
ENVIRONMENT=production
TZ=Europe/Kiev
```

### 2.3 Configure Port

- **Port:** `8080`
- **Health Check:** `/health`

### 2.4 Resources (Free Tier)

- **Plan:** `nf-compute-10` (0.1 vCPU, 256MB) - FREE
- **Instances:** 1

---

## Step 3: Deploy Telegram Bot

### 3.1 Create Service

1. **Add Service → Combined Service**
2. **Name:** `telegram-bot`
3. **Repository:** Same GitHub repo
4. **Branch:** `main`
5. **Build:**
   - Context: `/telegram_bot`
   - Dockerfile: `Dockerfile.northflank`

### 3.2 Set Environment Variables

```
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
DATABASE_URL=postgresql://postgres.[PROJECT]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
BACKEND_URL=https://backend-[PROJECT].northflank.app
TZ=Europe/Kiev
```

### 3.3 Resources (Free Tier)

- **Plan:** `nf-compute-10` (0.1 vCPU, 256MB) - FREE
- **Instances:** 1
- **No port needed** (bot uses polling)

---

## Step 4: Update Frontend

Set environment variable in Vercel/Cloudflare:

```
REACT_APP_API_URL=https://backend-[PROJECT].northflank.app
```

---

## Step 5: Get Supabase Connection String

1. Go to https://supabase.com/dashboard
2. Select your project
3. **Settings → Database**
4. Copy **Connection string (URI)**
5. Replace `[YOUR-PASSWORD]` with your database password

**Use the Pooler connection** (port 6543) for serverless:
```
postgresql://postgres.[PROJECT]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
```

---

## Architecture

```
┌──────────────┐       ┌─────────────────────────────────┐
│   Vercel     │       │         Northflank              │
│  (Frontend)  │       │                                 │
│              │──────▶│  ┌─────────────────────────┐   │
└──────────────┘       │  │  Backend (FastAPI)      │   │
                       │  │  0.1 vCPU, 256MB        │   │
                       │  │  Port 8080              │   │
                       │  └───────────┬─────────────┘   │
                       │              │                  │
                       │  ┌───────────┴─────────────┐   │
                       │  │  Telegram Bot           │   │
                       │  │  0.1 vCPU, 256MB        │   │
                       │  └───────────┬─────────────┘   │
                       └──────────────┼─────────────────┘
                                      │
                                      ▼
                       ┌──────────────────────────────┐
                       │        Supabase              │
                       │      (PostgreSQL)            │
                       │         FREE                 │
                       └──────────────────────────────┘
```

---

## ⚠️ Important Notes

### Memory Optimization

256MB is tight. Add to backend `.env`:

```
# Reduce workers for low memory
WEB_CONCURRENCY=1
```

### If Out of Memory

Upgrade to `nf-compute-20` (0.2 vCPU, 512MB) for ~$5/month

---

## Useful Commands

### View Logs
- Northflank Dashboard → Services → Logs

### Restart Service
- Dashboard → Service → Restart

### Check Health
```bash
curl https://backend-[PROJECT].northflank.app/health
```

---

## Troubleshooting

### "Out of Memory"
- Reduce dependencies
- Use `--workers 1` in uvicorn
- Upgrade compute plan

### "Connection Refused to Database"
- Check Supabase connection string
- Use pooler URL (port 6543)
- Check IP allowlist in Supabase

### "CORS Error"
- Update `CORS_ORIGINS` env var
- Include your frontend URL
