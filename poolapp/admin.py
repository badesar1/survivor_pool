from django.contrib import admin

# Register your models here.
from .models import League, UserProfile, Profile, Week, Contestant, Pick

@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'creator')
    search_fields = ('name', 'creator__username')
    filter_horizontal = ('members',)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'league', 'eliminated', 'immunity_idols', 'total_score')
    search_fields = ('user__username', 'league__name')
    list_filter = ('league', 'eliminated')

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'bio', 'avatar')
    search_fields = ('user__username',)

@admin.register(Week)
class WeekAdmin(admin.ModelAdmin):
    list_display = ('number', 'league', 'start_date', 'lock_time')
    search_fields = ('league__name',)
    list_filter = ('league', 'number')

@admin.register(Contestant)
class ContestantAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    search_fields = ('name',)
    list_filter = ('is_active',)

@admin.register(Pick)
class PickAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'week', 'safe_pick', 'voted_out_pick', 'imty_challenge_winner_pick', 'used_immunity_idol')
    search_fields = ('user_profile__user__username', 'league__name')
    list_filter = ('week__league', 'used_immunity_idol')