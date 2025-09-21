from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile, League, Week, Profile
from django.conf import settings
import datetime
from zoneinfo import ZoneInfo
from django.utils import timezone
import logging
from django_celery_beat.models import PeriodicTask, ClockedSchedule
from datetime import timedelta
import json

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        logger.info(f"Profile created for user '{instance.username}'.")

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

@receiver(post_save, sender=League)
def add_creator_to_league(sender, instance, created, **kwargs):
    if created:
        # Add the creator to the league's members
        instance.members.add(instance.creator)
        logger.info(f"Added creator '{instance.creator.username}' to League '{instance.name}' members.")
        # Log the current leagues of the user for debugging
        user_leagues = instance.creator.leagues.all()
        league_names = ", ".join([league.name for league in user_leagues])
        logger.debug(f"User '{instance.creator.username}' is now a member of leagues: {league_names}")

@receiver(m2m_changed, sender=League.members.through)
def create_user_league_profile(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "post_add":
        for user_id in pk_set:
            try:
                user = User.objects.get(pk=user_id)
                profile, created = UserProfile.objects.get_or_create(user=user, league=instance)
                if created:
                    logger.info(f"UserProfile created for '{user.username}' in League '{instance.name}'.")
                else:
                    logger.debug(f"UserProfile already exists for '{user.username}' in League '{instance.name}'.")
            except User.DoesNotExist:
                logger.error(f"User with id '{user_id}' does not exist.")
            except Exception as e:
                logger.error(f"Unexpected error while creating UserProfile for user_id '{user_id}' in League '{instance.name}': {e}")

@receiver(post_save, sender=League)
def create_weeks_for_league(sender, instance, created, **kwargs):
    if not created:
        return

    season = getattr(settings, 'CURRENT_SEASON', 49)
    cfg = settings.SEASON_CONFIG.get(season)
    if not cfg:
        logger.error(f"No SEASON_CONFIG for season {season}. Skipping week creation.")
        return

    start_date = cfg["START_DATE"]
    episodes = cfg["EPISODES"]
    lock_hour = cfg.get("LOCK_HOUR_ET", 20)
    lock_weekday = cfg.get("LOCK_WEEKDAY", 2)  # default Wednesday
    eastern = ZoneInfo("America/New_York")

    # If weeks for this league+season already exist, do nothing (idempotent)
    if Week.objects.filter(league=instance, season=season).exists():
        logger.info(f"Weeks already present for league '{instance.name}' season {season}; skipping.")
        return

    created_count = 0
    for week_number in range(1, episodes + 1):
        # derive start_date for each week
        wk_start = start_date + datetime.timedelta(weeks=week_number - 1)

        # compute lock_time on configured weekday @ lock_hour ET
        days_to_target = (lock_weekday - wk_start.weekday()) % 7
        lock_date = wk_start + datetime.timedelta(days=days_to_target)
        naive_lock = datetime.datetime(
            lock_date.year, lock_date.month, lock_date.day,
            lock_hour, 0, 0, 0
        )
        lock_dt = timezone.make_aware(naive_lock, eastern)

        _, created_row = Week.objects.get_or_create(
            league=instance, season=season, number=week_number,
            defaults={'start_date': wk_start, 'lock_time': lock_dt}
        )
        created_count += int(created_row)

    logger.info(f"Created {created_count} week(s) for league '{instance.name}' season {season}.")

@receiver(post_save, sender=Week)
def schedule_week_reminder(sender, instance, created, **kwargs):
    """
    Automatically schedule or update a Celery-Beat periodic task
    to send reminders 2 hours before the week's lock_time.
    """
    # Calculate the reminder time (2 hours before lock_time)
    reminder_time = instance.lock_time - timedelta(hours=2)

    # Ensure the time is valid
    if reminder_time <= timezone.now():
        return  # Skip scheduling if the reminder time is in the past

    # Create or update the ClockedSchedule
    clocked_schedule, _ = ClockedSchedule.objects.get_or_create(
        clocked_time=reminder_time
    )

    # Create or update the PeriodicTask
    task_name = f"Send reminder for Week {instance.number} in {instance.league.name}"
    PeriodicTask.objects.update_or_create(
        name=task_name,
        defaults={
            'task': 'poolapp.tasks.send_reminder_emails_for_week',  # Adjust based on your task path
            'clocked': clocked_schedule,
            'args': json.dumps([instance.id]),  # Pass the week ID as an argument
            'one_off': True,  # Ensure the task runs only once
        }
    )