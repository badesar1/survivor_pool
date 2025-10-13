# Render Deployment Fixes

## Issue 1: Migration Error ✅ FIXED

**Problem:** Migration 0006 tried to add `season` column that already existed in production DB.

**Solution:** Rewrote migration 0006 to safely check if columns exist before adding them.

**Status:** ✅ Migration file updated - will deploy successfully now.

---

## Issue 2: Email Reminders Not Working

### Root Cause Analysis

Your email reminders aren't working because **Celery workers and Celery Beat aren't running on Render**.

### Current Setup (Not Working):
- ✅ Celery is installed (`celery==5.4.0`)
- ✅ Redis is configured (`CELERY_BROKER_URL`)
- ✅ django-celery-beat is installed
- ✅ Tasks are defined in `poolapp/tasks.py`
- ✅ Signals schedule tasks in `poolapp/signals.py`
- ❌ **No Celery worker process running**
- ❌ **No Celery Beat scheduler running**

### What Needs to Happen:

On Render, you need **3 separate services**:
1. **Web Service** - Your Django app (already running ✅)
2. **Worker Service** - Celery worker to execute tasks (MISSING ❌)
3. **Beat Service** - Celery Beat scheduler to trigger tasks on schedule (MISSING ❌)

---

## Solution: Add Celery Workers on Render

### Step 1: Verify Redis is Running

In your Render dashboard, check if you have a Redis instance. If not:
1. Go to Render Dashboard
2. Click "New +" → "Redis"
3. Create a Redis instance
4. Copy the **Internal Redis URL**
5. Add to environment variable: `CELERY_BROKER_URL=redis://...`

### Step 2: Create Celery Worker Service

In Render Dashboard:

1. **Click "New +" → "Background Worker"**
2. **Configure:**
   - Name: `survivor-pool-celery-worker`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `celery -A survivor_pool worker --loglevel=info`
   - Instance Type: `Starter` (free tier OK)

3. **Add Environment Variables** (same as web service):
   ```
   DJANGO_SETTINGS_MODULE=survivor_pool.settings
   SECRET_KEY=<your-secret-key>
   DATABASE_URL=<your-postgres-url>
   CELERY_BROKER_URL=<your-redis-url>
   EMAIL_HOST=<your-smtp-host>
   EMAIL_PORT=<your-smtp-port>
   EMAIL_HOST_USER=<your-email>
   EMAIL_HOST_PASSWORD=<your-password>
   DEFAULT_FROM_EMAIL=<your-from-email>
   ```

### Step 3: Create Celery Beat Service

In Render Dashboard:

1. **Click "New +" → "Background Worker"**
2. **Configure:**
   - Name: `survivor-pool-celery-beat`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `celery -A survivor_pool beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler`
   - Instance Type: `Starter` (free tier OK)

3. **Add Environment Variables** (same as web service and worker)

---

## Alternative: Single Procfile Approach (If Render Supports)

If you're on a platform that uses Procfile (like Heroku), create this file:

**Procfile:**
```
web: gunicorn survivor_pool.wsgi:application --bind 0.0.0.0:$PORT
worker: celery -A survivor_pool worker --loglevel=info
beat: celery -A survivor_pool beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

But **Render doesn't use Procfile** - you need separate services.

---

## Verification Steps

### 1. Check if Worker is Running

In Render Dashboard → Celery Worker Logs, you should see:
```
[2025-10-13 12:00:00,000: INFO/MainProcess] Connected to redis://...
[2025-10-13 12:00:00,000: INFO/MainProcess] celery@worker ready.
```

### 2. Check if Beat is Running

In Render Dashboard → Celery Beat Logs, you should see:
```
[2025-10-13 12:00:00,000: INFO/MainProcess] beat: Starting...
[2025-10-13 12:00:00,000: INFO/MainProcess] Scheduler: django_celery_beat.schedulers.DatabaseScheduler
```

### 3. Test Email Task Manually

SSH into your Render shell or use Django admin:
```python
from poolapp.tasks import send_reminder_emails_for_week
result = send_reminder_emails_for_week.delay(week_id=1, debug=True)
```

You should see email sending in worker logs.

### 4. Check Scheduled Tasks

In Django Admin → Periodic Tasks, you should see:
- Tasks created by `poolapp/signals.py` (line 98-125)
- Each week should have a scheduled reminder 2 hours before lock time

---

## Common Issues & Fixes

### Issue: "Connection refused" error in worker logs
**Fix:** Redis URL is wrong. Check `CELERY_BROKER_URL` environment variable.

### Issue: Worker starts but can't import Django
**Fix:** Add `DJANGO_SETTINGS_MODULE=survivor_pool.settings` to worker environment variables.

### Issue: Beat runs but tasks don't execute
**Fix:** Worker isn't running. Both beat AND worker must be running simultaneously.

### Issue: Tasks execute but emails don't send
**Fix:** Check email environment variables:
```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password  # NOT your regular password!
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=your-email@gmail.com
```

**For Gmail:** You need an "App Password", not your regular password:
1. Go to Google Account → Security
2. Enable 2-Factor Authentication
3. Create App Password for "Mail"
4. Use that 16-character password as `EMAIL_HOST_PASSWORD`

---

## Cost Estimate

On Render:
- **Web Service:** $0-7/month (Starter)
- **Celery Worker:** $0-7/month (Starter)
- **Celery Beat:** $0-7/month (Starter)
- **Redis:** $0 (free 25 MB) or $10/month (1 GB)

**Total:** Free tier should work fine for small leagues!

---

## Testing Checklist

After deploying all three services:

- [ ] Web service is running (main app loads)
- [ ] Redis is connected (check in Render dashboard)
- [ ] Celery Worker logs show "celery@worker ready"
- [ ] Celery Beat logs show "beat: Starting..."
- [ ] Django Admin → Periodic Tasks shows scheduled reminders
- [ ] Test email task manually (check worker logs for success)
- [ ] Wait for scheduled time and check if email arrives

---

## Quick Debug: Is Celery Even Needed?

**Alternative Option:** If you don't want to run 3 services, you can **disable Celery** and use a simpler cron-based approach:

1. **Remove Celery completely**
2. **Use Render's Cron Jobs** feature
3. **Create a management command** to send emails
4. **Schedule it to run every hour**

This is simpler but less flexible. Let me know if you want this approach instead!

---

## Summary

**To fix email reminders:**
1. ✅ Migration 0006 is fixed (deploy will work)
2. ❌ Create Celery Worker service on Render
3. ❌ Create Celery Beat service on Render
4. ❌ Verify Redis connection
5. ❌ Add all environment variables to both services
6. ❌ Deploy and check logs

**Once these 3 services are running, emails will work automatically!** 📧

Let me know if you want help with any specific step or if you'd prefer the simpler cron-based approach instead.

