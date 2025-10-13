# Celery Workers Diagnostic Guide

## Step 1: Check Worker Logs in Render Dashboard

### Celery Worker Logs

Go to Render Dashboard → `survivor-pool-celery-worker` → **Logs** tab

**✅ WORKING - You should see:**
```
[INFO/MainProcess] Connected to redis://red-xxxxx.oregon-postgres.render.com:6379/0
[INFO/MainProcess] mingle: searching for neighbors
[INFO/MainProcess] mingle: all alone
[INFO/MainProcess] celery@<hostname> ready.
[INFO/MainProcess] Task poolapp.tasks.send_reminder_emails_for_week[...] received
```

**❌ NOT WORKING - You might see:**
```
[ERROR/MainProcess] consumer: Cannot connect to redis://...
[CRITICAL/MainProcess] Unrecoverable error: ConnectionRefusedError
```
→ **Fix:** Redis URL is wrong or Redis isn't running

```
ModuleNotFoundError: No module named 'survivor_pool'
ImportError: cannot import name 'settings'
```
→ **Fix:** Missing `DJANGO_SETTINGS_MODULE` environment variable

```
[WARNING/MainProcess] No tasks found
```
→ **Fix:** Celery can't discover tasks, check `survivor_pool/__init__.py`

---

### Celery Beat Logs

Go to Render Dashboard → `survivor-pool-celery-beat` → **Logs** tab

**✅ WORKING - You should see:**
```
[INFO/MainProcess] beat: Starting...
[INFO/MainProcess] Scheduler: django_celery_beat.schedulers.DatabaseScheduler
[INFO/MainProcess] DatabaseScheduler: Schedule changed.
[INFO/MainProcess] Writing entries...
```

**❌ NOT WORKING - You might see:**
```
django.db.utils.OperationalError: could not connect to server
```
→ **Fix:** Database URL is wrong or missing

```
[ERROR/MainProcess] Scheduler: Cannot connect to database
```
→ **Fix:** Missing database environment variables

---

## Step 2: Check Environment Variables

Both Celery services need these environment variables:

### Required Variables Checklist:

**In Render Dashboard → Worker/Beat Service → Environment:**

- [ ] `DJANGO_SETTINGS_MODULE=survivor_pool.settings`
- [ ] `SECRET_KEY=<your-secret-key>`
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS=your-app.onrender.com`
- [ ] `DATABASE_URL=postgresql://...` (or separate DB_* vars)
- [ ] `CELERY_BROKER_URL=redis://...`
- [ ] `EMAIL_HOST=smtp.gmail.com` (or your SMTP host)
- [ ] `EMAIL_PORT=587`
- [ ] `EMAIL_HOST_USER=your-email@gmail.com`
- [ ] `EMAIL_HOST_PASSWORD=<app-password>`
- [ ] `DEFAULT_FROM_EMAIL=your-email@gmail.com`

**Common Mistake:** Forgetting to add database credentials to worker services!

---

## Step 3: Check Django Admin for Scheduled Tasks

1. Go to your Django Admin: `https://your-app.onrender.com/admin/`
2. Navigate to **Django Celery Beat → Periodic Tasks**

**✅ You should see:**
- Multiple tasks like "Send reminder for Week 1 in YourLeagueName"
- Each task should show:
  - **Task:** `poolapp.tasks.send_reminder_emails_for_week`
  - **Clocked:** A specific date/time (2 hours before week lock time)
  - **Enabled:** ✓
  - **One-off:** ✓

**❌ If you see nothing:**
- Signals aren't creating tasks
- Weeks might not exist yet
- Check that `django_celery_beat` is in `INSTALLED_APPS`

---

## Step 4: Manual Task Test

### Test via Django Shell (Render Console)

1. In Render Dashboard → Web Service → **Shell** tab
2. Run:

```python
python manage.py shell

# Then in shell:
from poolapp.tasks import send_reminder_emails_for_week
from poolapp.models import Week

# Get a week
week = Week.objects.first()
print(f"Testing with week {week.id}")

# Send test email (with debug=True to bypass time check)
result = send_reminder_emails_for_week.delay(week.id, debug=True)
print(f"Task ID: {result.id}")
print(f"Task state: {result.state}")
```

3. **Check Worker Logs immediately** - you should see:
```
[INFO/MainProcess] Task poolapp.tasks.send_reminder_emails_for_week[<task-id>] received
[INFO/ForkPoolWorker-1] Task poolapp.tasks.send_reminder_emails_for_week[<task-id>] succeeded in 2.5s
```

4. **Check your email inbox** - you should receive test emails

---

## Step 5: Check Task Results in Database

If you have database access, run:

```sql
-- Check if tasks are being created
SELECT * FROM django_celery_beat_periodictask 
WHERE name LIKE '%reminder%' 
ORDER BY id DESC 
LIMIT 5;

-- Check task execution history
SELECT * FROM django_celery_beat_clockedschedule 
ORDER BY clocked_time DESC 
LIMIT 10;
```

---

## Step 6: Test Email Configuration

Sometimes workers are running but emails fail. Test email settings:

### In Django Shell:

```python
from django.core.mail import send_mail
from django.conf import settings

print(f"EMAIL_HOST: {settings.EMAIL_HOST}")
print(f"EMAIL_PORT: {settings.EMAIL_PORT}")
print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")

# Try sending test email
send_mail(
    subject='Test Email from Survivor Pool',
    message='If you receive this, email is working!',
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=['your-email@example.com'],
    fail_silently=False,
)

print("Email sent successfully!")
```

**If this fails:**
- Check Gmail App Password (not regular password!)
- Check EMAIL_HOST_PASSWORD is set
- Check EMAIL_USE_TLS=True in settings.py
- Check firewall/security settings

---

## Common Issues & Solutions

### Issue 1: Workers Start Then Immediately Stop

**Symptom:** Logs show startup messages then nothing

**Likely Causes:**
- Worker crashed due to missing dependencies
- Out of memory on free tier
- Database connection closed

**Fix:**
- Check the very end of logs for error message
- Upgrade to paid tier for more memory
- Add database connection pooling

---

### Issue 2: Beat Shows "No schedule entry" or "Empty schedule"

**Symptom:** Beat logs show it's running but no tasks scheduled

**Likely Causes:**
- No Week objects in database
- Signals didn't fire when Weeks were created
- Scheduled times are in the past

**Fix:**
```python
# In Django shell:
from poolapp.models import Week
from poolapp.signals import schedule_week_reminder

# Re-schedule all weeks
for week in Week.objects.all():
    schedule_week_reminder(sender=Week, instance=week, created=False)
    print(f"Scheduled reminders for week {week.number}")
```

---

### Issue 3: Tasks Execute But No Emails Sent

**Symptom:** Worker logs show "Task succeeded" but no emails arrive

**Likely Causes:**
- Email going to spam
- Wrong recipient email addresses
- Email service blocking
- Incorrect FROM address

**Fix:**
- Check spam/junk folder
- Verify users have valid email addresses: `User.objects.filter(email__isnull=False)`
- Check FROM email matches authenticated email
- Try different email provider (SendGrid, Mailgun)

---

### Issue 4: Redis Connection Errors

**Symptom:** `ConnectionRefusedError` or `Connection refused`

**Likely Causes:**
- Redis URL is wrong
- Redis service isn't running
- Network/firewall blocking connection

**Fix:**
- In Render Dashboard, go to Redis instance
- Copy **Internal Redis URL** (starts with `redis://red-...`)
- Update `CELERY_BROKER_URL` in both worker services
- Make sure Redis is on same Render region as workers

---

## Quick Diagnostic Commands

Run these in Render Shell to get instant diagnostics:

```bash
# Check if Redis is accessible
python manage.py shell -c "from django.conf import settings; print(settings.CELERY_BROKER_URL)"

# Check if Celery can connect
python -c "from celery import Celery; app = Celery('test', broker='YOUR_REDIS_URL'); print(app.connection().connect())"

# List all scheduled tasks
python manage.py shell -c "from django_celery_beat.models import PeriodicTask; [print(t.name) for t in PeriodicTask.objects.all()]"

# Count users with email addresses
python manage.py shell -c "from django.contrib.auth.models import User; print(f'{User.objects.filter(email__isnull=False).count()} users with emails')"
```

---

## Success Criteria Checklist

Your workers are working correctly if ALL are true:

- [ ] Worker logs show "celery@worker ready"
- [ ] Beat logs show "DatabaseScheduler: Schedule changed"
- [ ] Django Admin shows periodic tasks
- [ ] Manual test task executes (Step 4)
- [ ] Test email arrives in inbox
- [ ] Worker logs show task execution (no errors)
- [ ] No Redis connection errors in logs
- [ ] Users have valid email addresses in database

---

## What to Send Me for Diagnosis

If you're still stuck, share:

1. **Last 20 lines of Worker logs**
2. **Last 20 lines of Beat logs**
3. **Environment variables list** (hide sensitive values!)
4. **Django Admin screenshot** of Periodic Tasks
5. **Result of manual task test** (Step 4)

I can diagnose the exact issue from these! 🔍

