from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .models import *
from django.contrib import messages
from .forms import PickForm, ExtendedUserCreationForm
import logging

logger = logging.getLogger('poolapp')

def register(request):
    if request.method == 'POST':
        form = ExtendedUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Your account has been created! You can now log in.')
            return redirect('login')  # Adjust redirect as needed
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExtendedUserCreationForm()
    
    return render(request, 'registration/register.html', {'form': form})


@login_required
def create_league(request):
    message = None
    if request.method == 'POST':
        league_name = request.POST.get('league_name')
        if not league_name:
            message = "League name cannot be empty."
            logger.warning(f"User '{request.user.username}' attempted to create a league without a name.")
            return render(request, 'create_league.html', {'message': message})
        try:
            with transaction.atomic():
                league = League.objects.create(name=league_name, creator=request.user)
                # Signal 'add_creator_to_league' will handle adding the user to 'members'
                logger.info(f"League '{league.name}' created by '{request.user.username}'.")
            messages.success(request, f"League '{league.name}' created successfully.")
            return redirect('poolapp:league_detail', league_id=league.id)
        except IntegrityError:
            message = f"A league with the name '{league_name}' already exists. Please choose a different name."
            logger.error(f"IntegrityError: League creation failed for name '{league_name}' by user '{request.user.username}'.")
        except Exception as e:
            message = "An unexpected error occurred while creating the league."
            logger.error(f"Unexpected error during league creation by user '{request.user.username}': {e}")
    return render(request, 'create_league.html', {'message': message})

@login_required
def join_league(request):
    query = request.GET.get('q', '')  # The search query if provided
    results = []

    # If there's a query, filter leagues by the query
    if query:
        results = League.objects.filter(name__icontains=query)

    if request.method == 'POST':
        league_id = request.POST.get('league_id')
        if league_id:
            try:
                league = League.objects.get(id=league_id)
                if request.user in league.members.all():
                    messages.info(request, "You are already a member of this league.")
                    logger.info(f"User '{request.user.username}' attempted to join League '{league.name}' but is already a member.")
                else:
                    league.members.add(request.user)
                    messages.success(request, f"You have successfully joined the league '{league.name}'.")
                    logger.info(f"User '{request.user.username}' joined League '{league.name}'.")
                return redirect('poolapp:league_detail', league_id=league.id)
            except League.DoesNotExist:
                messages.error(request, "The selected league does not exist.")
                logger.error(f"User '{request.user.username}' attempted to join a non-existent league with id '{league_id}'.")
    
    return render(request, 'join_league.html', {
        'query': query,
        'results': results
    })

@login_required
def make_picks(request, league_id, week_number):
    """
    Handles making/updating picks and resetting picks for a given league and week.
    """
    # Retrieve the League and Week instances
    league = get_object_or_404(League, id=league_id)
    week = get_object_or_404(Week, number=week_number, league=league)

    # Ensure the logged-in user is a member of the league
    if request.user not in league.members.all():
        messages.error(request, "You are not a member of this league.")
        logger.warning(f"User {request.user.username} attempted to access League {league.id} without membership.")
        return redirect('poolapp:dashboard')
    
    # Retrieve the UserProfile instance for the current user
    profile, created = UserProfile.objects.get_or_create(user=request.user, league=league)
    if created:
        logger.info(f"UserProfile created for {request.user.username} in League '{league.name}'.")

    # Determine if the user has at least one immunity idol
    has_immunity_idol = profile.immunity_idols > 0 
    if request.method == 'POST':
        if 'reset_picks' in request.POST:
            # Handle reset action
            current_time = timezone.now()
            if week.lock_time <= current_time:
                messages.error(request, "Cannot reset picks for a locked week.")
                logger.warning(f"User {request.user.username} attempted to reset picks for locked Week {week.number} in League {league.id}.")
                return redirect('poolapp:league_detail', league_id=league.id)
            try:
                pick = Pick.objects.get(user_profile=profile, week=week)
                if pick.used_immunity_idol:
                    profile.immunity_idols += 1  # Return the idol
                    profile.save()
                pick.delete()
                messages.success(request, f"Your picks for Week {week.number} have been reset.")
                logger.info(f"User {request.user.username} reset picks for Week {week.number} in League {league.id}.")
            except Pick.DoesNotExist:
                messages.info(request, "You have no picks to reset for this week.")
                logger.info(f"User {request.user.username} attempted to reset picks for Week {week.number} in League {league.id} but had no picks.")
            return redirect('poolapp:league_detail', league_id=league.id)
        
        elif 'submit_picks' in request.POST:
            # Handle pick submission
            # Fetch all active contestants
            all_active = Contestant.objects.filter(is_active=True)
            previous_picks = Pick.objects.filter(user_profile=profile, week__number__lt=week_number)
            existing_pick = Pick.objects.filter(user_profile=profile, week=week).first()

            if existing_pick:
                # Exclude all previous safe picks except the current one
                previously_safe_picks = previous_picks.exclude(id=existing_pick.id)
                previously_safe_chosen_ids = previously_safe_picks.values_list('safe_pick_id', flat=True)
            else:
                previously_safe_chosen_ids = previous_picks.values_list('safe_pick_id', flat=True)

            # Define available safe options, ensuring the current pick is included
            available_safe_options = all_active.exclude(id__in=previously_safe_chosen_ids)
            if existing_pick and existing_pick.safe_pick_id:
                available_safe_options = available_safe_options | Contestant.objects.filter(id=existing_pick.safe_pick_id)

            # Define available voted out options (no exclusions needed)
            available_voted_options = all_active

            form = PickForm(
                request.POST,
                instance=existing_pick,
                has_immunity_idol=has_immunity_idol,
                available_safe=available_safe_options,
                available_voted=available_voted_options,
            )

            # Validate form
            if form.is_valid():
                # Save form without committing to set additional fields
                # Retrieve cleaned data
                safe_pick = form.cleaned_data.get('safe_pick')
                voted_out_pick = form.cleaned_data.get('voted_out_pick')
                imty_challenge_winner_pick = form.cleaned_data.get('imty_challenge_winner_pick')
                use_idol = form.cleaned_data.get('used_immunity_idol')

                # Error handling: Ensure all picks are made
                if not safe_pick or not voted_out_pick or not imty_challenge_winner_pick:
                    if not safe_pick:
                        messages.error(request, "You must select a contestant for the Safe Pick.")
                    if not voted_out_pick:
                        messages.error(request, "You must select a contestant for the Vote Out Pick.")
                    if not imty_challenge_winner_pick:
                        messages.error(request, "You must select a contestant for the Immunity Challenge Winner Pick.")
                    return render(request, 'make_picks.html', {
                        'league': league,
                        'week': week,
                        'form': form,
                        'safe_pick_queryset': available_safe_options,
                        'voted_out_pick_queryset': available_voted_options,
                        'imty_challenge_winner_pick_queryset': all_active,
                        'has_immunity_idol': has_immunity_idol
                    })
                
                pick = form.save(commit=False)
                
                # Assign required ForeignKey fields
                pick.user_profile = profile
                #pick.league = league
                pick.week = week

                if existing_pick:
                    pick.imty_challenge_winner_pick = imty_challenge_winner_pick

                # Check if safe_pick was already chosen in previous weeks
                if safe_pick and safe_pick.id in previously_safe_chosen_ids and (not existing_pick or safe_pick != existing_pick.safe_pick):
                    messages.error(request, "You have already chosen this contestant as safe in a previous week.")
                    logger.error(f"User {request.user.username} attempted to choose a duplicate safe pick (Contestant ID {safe_pick.id}) for Week {week.number} in League {league.id}.")
                    return redirect('poolapp:make_picks', league_id=league.id, week_number=week.number)

                # Handle immunity idol usage
                if use_idol and has_immunity_idol:
                    if not existing_pick or not existing_pick.used_immunity_idol:
                        pick.used_immunity_idol = True
                        profile.immunity_idols -= 1
                        profile.immunity_idols_played += 1
                        profile.save()
                        logger.info(f"User {request.user.username} used an immunity idol for Week {week.number} in League {league.id}.")
                else:
                    if existing_pick and existing_pick.used_immunity_idol:
                        pick.used_immunity_idol = False
                        profile.immunity_idols += 1  # Return the idol
                        profile.save()
                        logger.info(f"User {request.user.username} did not use immunity idol for Week {week.number} in League {league.id}.")

                # Save the Pick instance
                pick.save()

                if existing_pick:
                    messages.success(request, f"Your picks for Week {week.number} have been updated.")
                    logger.info(f"User {request.user.username} updated picks for Week {week.number} in League {league.id}.")
                else:
                    messages.success(request, f"Your picks for Week {week.number} have been saved.")
                    logger.info(f"User {request.user.username} created picks for Week {week.number} in League {league.id}.")

                return redirect('poolapp:league_detail', league_id=league.id)
            else:
                # Form is invalid; errors will be displayed in the template
                messages.error(request, "Please correct the errors below.")
                logger.error(f"User {request.user.username} submitted invalid picks for Week {week.number} in League {league.id}.")
                # Proceed to render the form with errors
        else:
            messages.error(request, "Invalid form submission.")
            logger.error("POST request without 'reset_picks' or 'submit_picks'.")
            # Initialize the form as if it's a GET request
            all_active = Contestant.objects.filter(is_active=True)
            previous_picks = Pick.objects.filter(user_profile=profile, week__number__lt=week_number)
            existing_pick = Pick.objects.filter(user_profile=profile, week=week).first()

            if existing_pick:
                previously_safe_picks = previous_picks.exclude(id=existing_pick.id)
                previously_safe_chosen_ids = previously_safe_picks.values_list('safe_pick_id', flat=True)
            else:
                previously_safe_chosen_ids = previous_picks.values_list('safe_pick_id', flat=True)

            available_safe_options = all_active.exclude(id__in=previously_safe_chosen_ids)
            if existing_pick and existing_pick.safe_pick_id:
                available_safe_options = available_safe_options | Contestant.objects.filter(id=existing_pick.safe_pick_id)

            available_voted_options = all_active

            form = PickForm(
                instance=existing_pick,
                has_immunity_idol=has_immunity_idol,
                available_safe=available_safe_options,
                available_voted=available_voted_options,
            )
            
    else:
        # Initialize the form with existing picks if any
        all_active = Contestant.objects.filter(is_active=True)
        previous_picks = Pick.objects.filter(user_profile=profile, week__number__lt=week_number)
        existing_pick = Pick.objects.filter(user_profile=profile, week=week).first()

        if existing_pick:
            previously_safe_picks = previous_picks.exclude(id=existing_pick.id)
            previously_safe_chosen_ids = previously_safe_picks.values_list('safe_pick_id', flat=True)
        else:
            previously_safe_chosen_ids = previous_picks.values_list('safe_pick_id', flat=True)

        available_safe_options = all_active.exclude(id__in=previously_safe_chosen_ids)
        if existing_pick and existing_pick.safe_pick_id:
            available_safe_options = available_safe_options | Contestant.objects.filter(id=existing_pick.safe_pick_id)

        available_voted_options = all_active

        form = PickForm(
            instance=existing_pick,
            has_immunity_idol=has_immunity_idol,
            available_safe=available_safe_options,
            available_voted=available_voted_options,
        )

    # Fetch contestants for each category to pass to the template
    safe_pick_queryset = available_safe_options
    #print(safe_pick_queryset)
    voted_out_pick_queryset = Contestant.objects.filter(is_active=True)
    imty_challenge_winner_pick_queryset = Contestant.objects.filter(is_active=True)

    context = {
        'league': league,
        'week': week,
        'form': form,
        'safe_pick_queryset': safe_pick_queryset,
        'voted_out_pick_queryset': voted_out_pick_queryset,
        'imty_challenge_winner_pick_queryset': imty_challenge_winner_pick_queryset,
        'has_immunity_idol': has_immunity_idol  # Pass the flag to the template
    }
    return render(request, 'make_picks.html', context)

@login_required
def dashboard(request):
    user_leagues = request.user.leagues.all()
    recent_activity = Activity.objects.filter(league__in=user_leagues).order_by('-timestamp')[:5]
    context = {
        'recent_activity': recent_activity,
    }
    return render(request, 'dashboard.html', context)

@login_required
def league_detail(request, league_id=None):
    league = get_object_or_404(League, id=league_id)


    # Ensure all members have a UserProfile in this league
    # user_profiles, created = UserProfile.objects.get_or_create(user=request.user, league=league)
    # if created:
    #     logger.info(f"UserProfile created for '{request.user.username}' in League '{league.name}'.")
    
    # Get all members as user profiles
    member_profiles = UserProfile.objects.filter(league=league)

    # Sort members by correct_guesses desc (leaderboard)
    leaderboard = member_profiles.order_by('-total_score', 'eliminated')
    #print(leaderboard)

    for profile in leaderboard:
        profile.total_score = (
            profile.correct_guesses +
            profile.correct_imty_challenge_guesses +
            profile.immunity_idols_played +
            profile.immunity_idols
        )

    # Get all contestants that are still active
    active_contestants = Contestant.objects.filter(is_active=True)
    voted_out_contestants = Contestant.objects.filter(is_active=False)

    # Optional: Get the latest week or all weeks. For simplicity, let’s get all weeks.
    weeks = Week.objects.filter(league=league).order_by('number')

    # Determine current time
    current_time = timezone.now()

    # Identify the current week
    current_week = None
    for week in weeks:
        if current_time < week.lock_time:
            current_week = week
            break

    # Annotate each week with its status
    annotated_weeks = []
    for week in weeks:
        if week == current_week:
            status = 'current'
        elif week.lock_time < current_time:
            status = 'past'
        else:
            status = 'future'
        annotated_weeks.append({
            'week': week,
            'status': status,
            'lock_time': week.lock_time,
        })

    picks_by_week = {}
    for w in weeks:
        # Retrieve picks via UserProfile
        w_picks = Pick.objects.filter(week=w, user_profile__league=league).select_related(
            'user_profile__user', 'safe_pick', 'voted_out_pick', 'imty_challenge_winner_pick')
        # Create a dictionary mapping UserProfile IDs to Pick instances
        w_picks_dict = {p.user_profile.id: p for p in w_picks}
        picks_by_week[w.number] = w_picks_dict
        #print(picks_by_week)

    context = {
        'league': league,
        'leaderboard': leaderboard,
        'active_contestants': active_contestants,
        'voted_out_contestants': voted_out_contestants,
        'weeks': annotated_weeks,
        'picks_by_week': picks_by_week,
        'current_time': current_time,
        'current_week': current_week,
    }
    return render(request, 'league_detail.html', context)

@login_required
def user_profile(request, league_id, user_id):
    league = get_object_or_404(League, id=league_id)
    user = get_object_or_404(User, id=user_id)
    weeks = Week.objects.filter(league=league).order_by('number')
    picks = Pick.objects.filter(user_profile__user=user, week__league=league).order_by('week__number')

    # Ensure the user is a member of the league
    if user not in league.members.all():
        messages.error(request, "User is not a member of this league.")
        logger.warning(f"Attempt to access profile of user {user.username} who is not in league {league.id}.")
        return redirect('poolapp:league_detail', league_id=league.id)
    
    # Retrieve the league-specific UserProfile
    profile = get_object_or_404(UserProfile, user=user, league=league)

    current_time = timezone.now()

    user_stats = []
    for week in weeks:
        pick = picks.filter(week=week).first()
        result = None
        try:
            result = WeekResult.objects.get(week=week)
        except WeekResult.DoesNotExist:
            result = None  # No result for this week

        if pick:
            if result and result.voted_out_contestant:
                is_correct = pick.safe_pick != result.voted_out_contestant
                result_status = 'Safe' if is_correct else 'Fucked'
            else:
                result_status = 'Pending'

            user_stats.append({
                'week': week.number,
                'safe_pick': pick.safe_pick.name if pick.safe_pick else None,
                'voted_out_pick': pick.voted_out_pick.name if pick.voted_out_pick else None,
                'imty_challenge_winner_pick': pick.imty_challenge_winner_pick.name if pick.imty_challenge_winner_pick else None,
                'used_idol': pick.used_immunity_idol,
                'result': result_status,
                'lock_time': week.lock_time,
            })
        else:
            user_stats.append({
                'week': week.number,
                'safe_pick': None,
                'voted_out_pick': None,
                'imty_challenge_winner_pick': None,
                'used_idol': None,
                'result': 'No Pick',
                'lock_time': week.lock_time,
            })

    context = {
        'league': league,
        'user': user,
        'user_stats': user_stats,
        'current_time': current_time,
    }
    return render(request, 'user_profile.html', context)