from django.core.management.base import BaseCommand
from poolapp.models import Week, League, WeekResult, Pick, UserProfile, Contestant

class Command(BaseCommand):
    help = 'Update weekly results, account for immunity idols, and update user profiles.'

    def add_arguments(self, parser):
        parser.add_argument('week_number', type=int, help="Week number to update.")
        parser.add_argument('voted_out_contestant', type=str, help="Name of the contestant who was voted out.")
        parser.add_argument('imty_challenge_winner', type=str, help="Name of the contestant (or tribe)? that wom immunity.")

    def handle(self, *args, **options):
        week_number = options['week_number']
        voted_out_contestant_name = options['voted_out_contestant']
        imty_challenge_winner_name = options['imty_challenge_winner']

        # Fetch all leagues
        leagues = League.objects.all()

        for league in leagues:
            self.stdout.write(self.style.SUCCESS(f"Processing League: {league.name}"))

            try:
                week = Week.objects.get(number=week_number, league=league)
            except Week.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Week {week_number} does not exist."))
                return

            try:
                voted_out_contestant = Contestant.objects.get(name=voted_out_contestant_name)
                imty_challenge_winner = Contestant.objects.get(name=imty_challenge_winner_name)
            except Contestant.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Contestant '{voted_out_contestant_name}' does not exist."))
                return
            
            # Update the contestant status
            voted_out_contestant.is_active = False  # Assuming you have an `is_active` field in your Contestant model
            voted_out_contestant.save()
            self.stdout.write(self.style.SUCCESS(f"Marked contestant '{voted_out_contestant_name}' as voted out."))
            
            week_result, created = WeekResult.objects.get_or_create(week=week)
            week_result.voted_out_contestant = voted_out_contestant
            week_result.save()

            # Update the week's result
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created result for Week {week_number}."))
            else:
                self.stdout.write(self.style.SUCCESS(f"Updated result for Week {week_number}."))

            # Update user profiles based on picks
            picks = Pick.objects.filter(week=week)
            for pick in picks:
                profile = pick.user_profile

                if pick.imty_challenge_winner_pick == imty_challenge_winner:
                    profile.correct_imty_challenge_guesses += 1
                    profile.save()
                    self.stdout.write(self.style.SUCCESS(f"User {profile.user.username} earned a correct immunity challenge guess."))

                if not profile.eliminated:
                    # Check if the user used an immunity idol
                    if pick.used_immunity_idol:
                        self.stdout.write(f"User {profile.user.username} used an immunity idol for Week {week_number}.")
                        profile.immunity_idols -= 1
                        profile.immunity_idols_played += 1
                        profile.immunity_idols = max(0, profile.immunity_idols)
                        profile.save()

                    # Check if the user's safe pick was eliminated
                    if pick.safe_pick == voted_out_contestant and not pick.used_immunity_idol:
                        profile.eliminated = True
                        profile.save()
                        self.stdout.write(self.style.WARNING(f"User {profile.user.username} has been eliminated."))
                    else:
                        # Increment correct guesses if the user picked correctly
                        profile.correct_guesses += 1
                        profile.save()
                        self.stdout.write(self.style.SUCCESS(f"User {profile.user.username} earned a correct guess."))

                    # Award immunity idol for correctly guessing the voted-out contestant
                    if pick.voted_out_pick == voted_out_contestant:
                        profile.immunity_idols += 1
                        profile.save()
                        self.stdout.write(self.style.SUCCESS(f"User {profile.user.username} earned an immunity idol for correctly guessing the voted-out contestant."))