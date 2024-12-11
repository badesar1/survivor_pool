# poolapp/context_processors.py

from .models import League  # Adjust the import based on your project structure

def user_leagues(request):
    """
    Adds the list of leagues the current user is part of to the template context.
    """
    if request.user.is_authenticated:
        leagues = request.user.leagues.all()  # Adjust based on your User-League relationship
    else:
        leagues = []
    return {
        'user_leagues': leagues
    }