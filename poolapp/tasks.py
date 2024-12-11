from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from poolapp.models import Week  # Adjust import based on your app structure
from datetime import datetime, timedelta

@shared_task
def send_reminder_emails_for_week(week_id):
    from django.contrib.auth.models import User  # Import here to avoid circular imports

    try:
        # Fetch the Week object
        week = Week.objects.get(id=week_id)
        reminder_time = week.lock_time - timedelta(hours=2)

        # Check if the current time is within the reminder window
        now = datetime.now()
        if reminder_time <= now < week.lock_time:
            users = User.objects.all()  # Get all registered users
            for user in users:
                if user.email:
                    send_mail(
                        subject=f"Reminder: Make Your Picks for Week {week.number}",
                        message=(
                            f"Hi {user.username},\n\n"
                            f"Just a friendly reminder to make your picks for Week {week.number}! "
                            f"The picks lock at {week.lock_time.strftime('%Y-%m-%d %H:%M:%S')}.\n\n"
                            f"Good luck!"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                    )
            return f"Successfully sent reminders for Week {week.number}."
        else:
            return f"No reminders sent; current time is not within the reminder window for Week {week.number}."
    except Week.DoesNotExist:
        return f"Week with ID {week_id} does not exist."