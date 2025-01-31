from django.db import models
from django.contrib.auth.models import User
from zoneinfo import ZoneInfo
from django.conf import settings
import datetime
from django.utils import timezone
from django.core.exceptions import ValidationError


class League(models.Model):
    name = models.CharField(max_length=100, unique=True)
    members = models.ManyToManyField(User, related_name='leagues', blank=True)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_leagues')

    def __str__(self):
        return self.name

class Contestant(models.Model):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)  # True if still in the game
    bio = models.TextField(default="Bio not provided.")
    photo = models.ImageField(upload_to='contestants/photos/',default="default_images/Unknown1.jpeg")
    tribe = models.CharField(max_length=50, blank=True, null=True)
    bio_link = models.URLField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name
    
class Week(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='weeks')
    number = models.PositiveIntegerField()
    start_date = models.DateField(blank=True, null=True)
    lock_time = models.DateTimeField(blank=True, null=True)
    

    def save(self, *args, **kwargs):
        # If start_date not set, derive it from the season start date
        if not self.start_date:
            # Each week starts 7 days after the previous one:
            # Week 1: SEASON_START_DATE
            # Week 2: SEASON_START_DATE + 7 days
            # etc.
            self.start_date = settings.SEASON_START_DATE + datetime.timedelta(weeks=self.number - 1)

        # If lock_time not set, compute Wednesday 8pm of that week in EST
        if not self.lock_time:
            # Find upcoming Wednesday relative to start_date
            # weekday(): Monday=0, Tuesday=1, Wednesday=2, ...
            days_to_wednesday = (2 - self.start_date.weekday()) % 7
            wednesday_date = self.start_date + datetime.timedelta(days=days_to_wednesday)

            # Set lock_time to Wednesday 8pm EST
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
            lock_dt = timezone.make_aware(naive_lock_dt, timezone=eastern)
            self.lock_time = lock_dt

        super().save(*args, **kwargs)
        if not hasattr(self, 'result'):
            WeekResult.objects.create(week=self)

    def __str__(self):
        return f"Week {self.number} (Starts on {self.start_date})"

    class Meta:
        ordering = ['-number']

class WeekResult(models.Model):
    week = models.OneToOneField(Week, on_delete=models.CASCADE, related_name='result')
    voted_out_contestant = models.ForeignKey(Contestant, on_delete=models.SET_NULL, null=True)
    #imty_challenge_winner = models.ForeignKey(Contestant, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"Result for {self.week}: {self.voted_out_contestant}"

class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='league_profiles')
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='user_profiles')
    eliminated = models.BooleanField(default=False)
    immunity_idols = models.PositiveIntegerField(default=0)
    correct_guesses = models.PositiveIntegerField(default=0)  
    immunity_idols_played = models.PositiveIntegerField(default=0)
    correct_imty_challenge_guesses = models.PositiveIntegerField(default=0)
    total_score = models.PositiveIntegerField(default=0)
    has_returned = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'league')  # Ensures one profile per user per league

    def __str__(self):
        return f"{self.user.username} - {self.league.name}"
    
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    # Add any general user fields here, e.g., bio, avatar, etc.
    bio = models.TextField(blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"
    
class Activity(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    description = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.description} at {self.timestamp}"

class Pick(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    # league = models.ForeignKey(League, on_delete=models.CASCADE)
    week = models.ForeignKey(Week, on_delete=models.CASCADE)
    safe_pick = models.ForeignKey(Contestant, on_delete=models.CASCADE, related_name='safe_picks')
    voted_out_pick = models.ForeignKey(Contestant, on_delete=models.CASCADE, related_name='voted_out_picks')
    used_immunity_idol = models.BooleanField(default=False)
    imty_challenge_winner_pick = models.ForeignKey(Contestant, on_delete=models.CASCADE, related_name='imty_challenge_winner_picks')

    class Meta:
        unique_together = ('user_profile', 'week')
        indexes = [
            models.Index(fields=['user_profile']),
            #models.Index(fields=['league']),
            models.Index(fields=['week']),
        ]

    def clean(self):
        if self.safe_pick == self.voted_out_pick:
            raise ValidationError("Safe pick and voted out pick cannot be the same contestant.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user_profile.user.username} picks for Week {self.week.number}"