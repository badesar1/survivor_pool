# poolapp/management/commands/update_week_results.py

from django.core.management.base import BaseCommand
from django.db.models import Sum
from poolapp.models import Week, League, WeekResult, Pick, UserProfile, Contestant


class Command(BaseCommand):
    help = 'Update weekly results, apply Option 2 idol logic, wagers, parlay (all-or-nothing), and recompute scores idempotently.'

    def add_arguments(self, parser):
        parser.add_argument('week_number', type=int, help="Week number to update.")
        parser.add_argument('voted_out_contestant', type=str, help="Name of the contestant who was voted out.")
        parser.add_argument('imty_challenge_winner', type=str, help="Name of the contestant (or tribe) that won immunity.")

    def handle(self, *args, **options):
        week_number = options['week_number']
        voted_out_contestant_name = options['voted_out_contestant']
        imty_challenge_winner_name = options['imty_challenge_winner']

        leagues = League.objects.all()

        for league in leagues:
            self.stdout.write(self.style.SUCCESS(f"Processing League: {league.name}"))

            try:
                week = Week.objects.get(number=week_number, league=league)
            except Week.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Week {week_number} does not exist in league '{league.name}'."))
                continue

            try:
                voted_out_contestant = Contestant.objects.get(name=voted_out_contestant_name)
                imty_challenge_winner = Contestant.objects.get(name=imty_challenge_winner_name)
            except Contestant.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f"Contestant lookup failed for '{voted_out_contestant_name}' or '{imty_challenge_winner_name}'."
                ))
                continue

            # Mark the booted contestant inactive (visibility)
            if voted_out_contestant.is_active:
                voted_out_contestant.is_active = False
                voted_out_contestant.save()
                self.stdout.write(self.style.SUCCESS(f"Marked contestant '{voted_out_contestant_name}' as voted out."))

            # Persist the week's result
            week_result, created = WeekResult.objects.get_or_create(week=week)
            week_result.voted_out_contestant = voted_out_contestant
            week_result.save()
            self.stdout.write(self.style.SUCCESS(
                f"{'Created' if created else 'Updated'} result for Week {week_number}."
            ))

            # Determine whether immunity is tribe-based (multi-tribe) or individual (merge)
            n_tribes = Contestant.objects.values('tribe').distinct().count()
            winner_tribe = getattr(imty_challenge_winner, "tribe", None)

            # --- Ensure every member has a Pick row for this week (so we can evaluate missed weeks) ---
            profiles = UserProfile.objects.filter(league=league).select_related('user')
            existing_picks = {p.user_profile_id: p for p in Pick.objects.filter(week=week)}
            created_placeholders = 0
            for prof in profiles:
                if prof.id not in existing_picks:
                    p = Pick(user_profile=prof, week=week)  # blank pick
                    p.save()
                    existing_picks[prof.id] = p
                    created_placeholders += 1
            if created_placeholders:
                self.stdout.write(self.style.WARNING(f"Created {created_placeholders} placeholder pick(s) for users with no submission."))

            # Precompute prior-week idol availability (for auto-burn on no-pick)
            prior_available = {}
            for prof in profiles:
                prior_picks = Pick.objects.filter(
                    user_profile=prof, week__league=league, week__number__lt=week.number
                )
                earned_prior = prior_picks.filter(voted_out_pick_correct=True).count()
                used_prior = prior_picks.filter(used_immunity_idol=True).count()
                prior_available[prof.id] = max(0, earned_prior - used_prior)

            # Iterate all picks (now includes placeholders)
            picks = Pick.objects.filter(week=week).select_related(
                'user_profile', 'safe_pick', 'voted_out_pick', 'imty_challenge_winner_pick'
            )

            for pick in picks:
                profile = pick.user_profile

                # --- Auto-burn idol if NO picks and player had idol available prior to this week ---
                no_picks_submitted = (not pick.safe_pick and not pick.voted_out_pick and not pick.imty_challenge_winner_pick)
                if no_picks_submitted and not pick.used_immunity_idol and prior_available.get(profile.id, 0) > 0:
                    pick.used_immunity_idol = True
                    prior_available[profile.id] -= 1
                    self.stdout.write(self.style.WARNING(
                        f"Auto-burned an idol for {profile.user.username} (no picks submitted)."
                    ))

                # --- EXILE on missing Safe Pick (no idol to save) ---
                # If player has no safe pick and hasn't used/burned an idol, exile them (week > 1)
                if (not pick.safe_pick) and (not pick.used_immunity_idol) and (not profile.eliminated) and (week.number > 1):
                    profile.eliminated = True
                    profile.save()
                    self.stdout.write(self.style.WARNING(
                        f"{profile.user.username} had no Safe Pick and no idol: EXILED."
                    ))

                # --- Correctness flags ---
                # Safe survives (true if safe != boot)
                pick.safe_pick_correct = bool(pick.safe_pick and pick.safe_pick_id != voted_out_contestant.id)

                # Voted-out correctness
                pick.voted_out_pick_correct = bool(pick.voted_out_pick and pick.voted_out_pick_id == voted_out_contestant.id)

                # Immunity correctness (tribe vs individual)
                if pick.imty_challenge_winner_pick:
                    if n_tribes > 1 and winner_tribe:
                        pick.imty_challenge_winner_pick_correct = (
                            pick.imty_challenge_winner_pick.tribe == winner_tribe
                        )
                    else:
                        pick.imty_challenge_winner_pick_correct = (
                            pick.imty_challenge_winner_pick_id == imty_challenge_winner.id
                        )
                else:
                    pick.imty_challenge_winner_pick_correct = False

                # --- idol protects from safe-pick failure ---
                if (
                    pick.safe_pick_id == voted_out_contestant.id and
                    not pick.used_immunity_idol and
                    not profile.eliminated and
                    week.number > 1
                ):
                    profile.eliminated = True
                    profile.save()
                    self.stdout.write(self.style.WARNING(f"User {profile.user.username} has been exiled (Safe pick went home, no idol)."))

                # --- If already EXILED, a wrong safe pick => PERMANENT elimination ---
                # We mark "permanent" by setting has_returned=True as a sentinel.
                # (Consider updating return_from_exile to disallow buy-back when has_returned is True.)
                if (
                    profile.eliminated and                    # already exiled
                    (pick.safe_pick_id == voted_out_contestant.id) and
                    (not pick.used_immunity_idol) and
                    week.number > 1
                ):
                    # If they were already exiled and their safe pick was the boot again (no idol), they are eliminated outright.
                    profile.eliminated = True
                    profile.has_returned = True  # sentinel meaning "permanently eliminated"
                    profile.save()
                    self.stdout.write(self.style.ERROR(
                        f"{profile.user.username} was already exiled and hit a wrong Safe again: ELIMINATED (permanent)."
                    ))

                # ---------------------------
                #   PARLAY: all-or-nothing
                # ---------------------------
                # If parlay selected and BOTH aren't correct -> user gets nothing from VO/Immunity:
                # - Force both correctness flags to False (prevents idol from VO)
                # - Wagers will both count as losses
                parlay_all_or_nothing = False
                if getattr(pick, 'parlay', False):
                    if not (pick.voted_out_pick_correct and pick.imty_challenge_winner_pick_correct):
                        parlay_all_or_nothing = True
                        pick.voted_out_pick_correct = False
                        pick.imty_challenge_winner_pick_correct = False

                # --- Compute points (idempotent), store on Pick ---

                # Base points
                base_safe = 1 if pick.safe_pick_correct else 0
                base_vo = 3 if pick.voted_out_pick_correct else 0
                base_im = 2 if pick.imty_challenge_winner_pick_correct else 0

                # (Old exiled penalty was -1 on incorrect safe while exiled. You asked to change this to outright elimination.)
                # So we REMOVE the -1 penalty; elimination has already been handled above.

                # Wagers
                wv = getattr(pick, 'wager_voted_out', 0) or 0
                wi = getattr(pick, 'wager_immunity', 0) or 0

                if parlay_all_or_nothing:
                    # All-or-nothing: both treated as wrong -> lose both wagers, no base VO/IM points.
                    wager_gain_vo = -wv
                    wager_gain_im = -wi
                    points_wagers = wager_gain_vo + wager_gain_im
                    parlay_bonus = 0  # no bonus on a miss
                    # Base VO/IM are already zeroed by correctness flags above.
                else:
                    # Normal wager behavior
                    wager_gain_vo = (2 * wv) if pick.voted_out_pick_correct else -wv
                    # 1.5x floored to int
                    wager_gain_im = int(1.5 * wi) if pick.imty_challenge_winner_pick_correct else -wi
                    points_wagers = wager_gain_vo + wager_gain_im

                    # Parlay bonus if both correct
                    parlay_bonus = 0
                    if getattr(pick, 'parlay', False) and pick.voted_out_pick_correct and pick.imty_challenge_winner_pick_correct:
                        parlay_bonus = int(0.5 * (base_vo + base_im))

                # Assign component points
                pick.points_safe = base_safe
                pick.points_vo = base_vo
                pick.points_immunity = base_im
                pick.points_wagers = points_wagers
                pick.points_parlay = parlay_bonus

                pick.points_week_total = base_safe + base_vo + base_im + points_wagers + parlay_bonus
                pick.save()

            # --- Recompute aggregates from scratch for THIS league (idempotent) ---
            for prof in UserProfile.objects.filter(league=league):
                prof_picks = Pick.objects.filter(user_profile=prof)

                safe_correct = prof_picks.filter(safe_pick_correct=True).count()
                voted_correct = prof_picks.filter(voted_out_pick_correct=True).count()
                challenge_correct = prof_picks.filter(imty_challenge_winner_pick_correct=True).count()
                idols_used = prof_picks.filter(used_immunity_idol=True).count()

                total_points = prof_picks.aggregate(s=Sum('points_week_total'))['s'] or 0

                prof.correct_guesses = safe_correct
                prof.correct_imty_challenge_guesses = challenge_correct
                prof.immunity_idols_played = idols_used
                # Idols held = VO-correct minus idols used (clamped)
                prof.immunity_idols = max(0, voted_correct - idols_used)
                prof.total_score = total_points
                prof.save()

            self.stdout.write(self.style.SUCCESS(
                f"Week {week_number} processed for league '{league.name}'."
            ))