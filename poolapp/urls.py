# poolapp/urls.py

from django.urls import path
from . import views

app_name = 'poolapp'  # Defines the application namespace

urlpatterns = [
    path('', views.dashboard, name='dashboard'),  # General Dashboard
    path('register/', views.register, name='register'),
    path('league/<int:league_id>/', views.league_detail, name='league_detail'),  # League-Specific Dashboard
    path('create-league/', views.create_league, name='create_league'),  # Create League
    path('join-league/', views.join_league, name='join_league'),  # Join League
    #path('league/<int:league_id>/', views.league_detail, name='league_detail'),  # League Detail
    path('league/<int:league_id>/week/<int:week_number>/make-picks/', views.make_picks, name='make_picks'),  # Make Picks
    path('league/<int:league_id>/user/<int:user_id>/', views.user_profile, name='user_profile'),
]