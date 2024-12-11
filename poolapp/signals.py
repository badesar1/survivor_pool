from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile, League, Week, Profile
from django.conf import settings
import datetime
from zoneinfo import ZoneInfo
from django.utils import timezone
import logging

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
    if created:
        number_of_weeks = 10  # Define how many weeks per season
        #self.stdout = None  # Signals do not have access to Command's stdout

        for week_number in range(1, number_of_weeks + 1):
            # Calculate start_date
            start_date = settings.SEASON_START_DATE + datetime.timedelta(weeks=week_number - 1)

            # Calculate lock_time (Wednesday 8 PM EST)
            days_to_wednesday = (2 - start_date.weekday()) % 7  # 0=Monday, ..., 2=Wednesday
            wednesday_date = start_date + datetime.timedelta(days=days_to_wednesday)
            eastern = ZoneInfo("America/New_York")
            naive_lock_dt = datetime.datetime(
                year=wednesday_date.year,
                month=wednesday_date.month,
                day=wednesday_date.day,
                hour=20,
                minute=0,
                second=0,
                microsecond=0
            )
            lock_dt = timezone.make_aware(naive_lock_dt, eastern)

            # Create Week
            Week.objects.create(
                number=week_number,
                start_date=start_date,
                lock_time=lock_dt,
                league=instance
            )

# from django.db.models.signals import m2m_changed

# @receiver(m2m_changed, sender=League.members.through)
# def create_user_profile(sender, instance, action, reverse, pk_set, **kwargs):
#     if action == "post_add":
#         for user_id in pk_set:
#             UserProfile.objects.get_or_create(user_id=user_id, league=instance)

from django.db.models.signals import post_save
from django.dispatch import receiver
from django_celery_beat.models import PeriodicTask, ClockedSchedule
from django.utils import timezone
from datetime import timedelta
from .models import Week
import json

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