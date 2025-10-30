# poolapp/management/commands/update_week_results.py

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta
from poolapp.models import Week, League, WeekResult, Pick, UserProfile, Contestant
import random


class Command(BaseCommand):
    help = (
        "Update weekly results for CURRENT_SEASON: Option 2 idol logic, "
        "auto-burn idol on missed week else auto-assign Safe from active contestants, "
        "parlay (all-or-nothing), wagers, and idempotent aggregates. "
        "Skips weeks not within ±60 days of today."
    )

    def add_arguments(self, parser):
        parser.add_argument('week_number', type=int, help="Week number to update.")
        parser.add_argument('voted_out_contestant', type=str, help="Name of the contestant who was voted out.")
        parser.add_argument('imty_challenge_winner', type=str, help="Name of the contestant (or tribe) that won immunity.")

    # Deterministic picker so re-runs don't reshuffle
    def _stable_choice(self, candidates, seed_tuple):
        if not candidates:
            return None
        candidates = sorted(candidates, key=lambda c: (c.id, c.name))
        rnd = random.Random(hash(seed_tuple))
        return candidates[rnd.randrange(len(candidates))]

    def handle(self, *args, **options):
        season = getattr(settings, "CURRENT_SEASON", None)
        if season is None:
            self.stdout.write(self.style.ERROR("settings.CURRENT_SEASON is not set. Aborting."))
            return

        week_number = options['week_number']
        voted_out_contestant_name = options['voted_out_contestant']
        imty_challenge_winner_name = options['imty_challenge_winner']

        now = timezone.now()
        window = timedelta(days=60)

        leagues = League.objects.all()

        for league in leagues:
            self.stdout.write(self.style.SUCCESS(f"Processing League: {league.name} (Season {season})"))

            # Current-season week
            try:
                week = Week.objects.get(number=week_number, league=league, season=season)
            except Week.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f"Week {week_number} (Season {season}) does not exist in league '{league.name}'. Skipping."
                ))
                continue

            # ----- Recency guard (±60 days) -----
            ref_dt = week.lock_time
            if not ref_dt and week.start_date:
                naive = datetime(
                    year=week.start_date.year, month=week.start_date.month, day=week.start_date.day,
                    hour=12, minute=0, second=0, microsecond=0
                )
                ref_dt = timezone.make_aware(naive, timezone.get_current_timezone())

            if ref_dt:
                if ref_dt < (now - window) or ref_dt > (now + window):
                    self.stdout.write(self.style.NOTICE(
                        f"Skipping Week {week.number} (ref {ref_dt:%Y-%m-%d}) for '{league.name}': outside ±60 days."
                    ))
                    continue
            else:
                self.stdout.write(self.style.NOTICE(
                    f"Skipping Week {week.number} for '{league.name}': no lock_time/start_date to validate recency."
                ))
                continue
            # ------------------------------------

            # Current-season contestants
            try:
                voted_out_contestant = Contestant.objects.get(name=voted_out_contestant_name, season=season)
            except Contestant.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f"Contestant '{voted_out_contestant_name}' not found for Season {season}."
                ))
                continue

            # Immunity winner may be a contestant or (pre-merge) a tribe keyword
            try:
                imty_challenge_winner = Contestant.objects.get(name=imty_challenge_winner_name, season=season)
                winner_tribe = imty_challenge_winner.tribe
            except Contestant.DoesNotExist:
                imty_challenge_winner = None
                winner_tribe = imty_challenge_winner_name  # Treat arg as tribe string

            # Mark the booted contestant inactive (UX)
            if voted_out_contestant.is_active:
                voted_out_contestant.is_active = False
                voted_out_contestant.save()
                self.stdout.write(self.style.SUCCESS(f"Marked '{voted_out_contestant_name}' as voted out."))

            # Persist result
            week_result, created = WeekResult.objects.get_or_create(week=week)
            week_result.voted_out_contestant = voted_out_contestant
            week_result.save()
            self.stdout.write(self.style.SUCCESS(
                f"{'Created' if created else 'Updated'} result for Week {week_number}."
            ))

            # Tribe vs merge detection within current season
            n_tribes = Contestant.objects.filter(season=season).values('tribe').distinct().count()

            # All profiles in this league
            profiles = UserProfile.objects.filter(league=league).select_related('user')

            # Precompute prior-week idol availability (current season)
            prior_available = {}
            for prof in profiles:
                prior_picks = Pick.objects.filter(
                    user_profile=prof,
                    week__league=league,
                    week__season=season,
                    week__number__lt=week.number
                )
                earned_prior = prior_picks.filter(voted_out_pick_correct=True).count()   # each VO correct earns an idol
                used_prior = prior_picks.filter(used_immunity_idol=True).count()
                prior_available[prof.id] = max(0, earned_prior - used_prior)

            # Map existing picks for this week
            existing_picks = {p.user_profile_id: p for p in Pick.objects.filter(week=week)}

            # Active contestants (current season) for auto-assign Safe
            active_contestants = list(Contestant.objects.filter(season=season, is_active=True))

            # For any profile missing a Pick, create a **non-blank** Pick:
            # 1) If idol available -> create with used_immunity_idol=True
            # 2) Else -> auto-assign Safe from unused active contestants
            created_count = 0
            for prof in profiles:
                if prof.id in existing_picks:
                    continue

                if prior_available.get(prof.id, 0) > 0:
                    pick = Pick.objects.create(
                        user_profile=prof,
                        week=week,
                        used_immunity_idol=True,
                        auto_assigned=True
                    )
                    prior_available[prof.id] -= 1
                    existing_picks[prof.id] = pick
                    created_count += 1
                    self.stdout.write(self.style.WARNING(
                        f"Auto-burned an idol for {prof.user.username} (missed week)."
                    ))
                else:
                    # determine unused safe candidates
                    prev_safe_ids = set(
                        Pick.objects.filter(
                            user_profile=prof,
                            week__league=league,
                            week__season=season,
                            week__number__lt=week.number
                        ).values_list('safe_pick_id', flat=True)
                    )
                    candidates = [c for c in active_contestants if c.id not in prev_safe_ids]
                    chosen = self._stable_choice(candidates, (prof.id, week.id))
                    pick = Pick.objects.create(
                        user_profile=prof,
                        week=week,
                        safe_pick=chosen,  # may be None if no candidates remain
                        auto_assigned=True
                    )
                    existing_picks[prof.id] = pick
                    created_count += 1
                    if chosen:
                        self.stdout.write(self.style.WARNING(
                            f"Auto-assigned Safe Pick for {prof.user.username}: {chosen.name}"
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"No available Safe candidate to auto-assign for {prof.user.username}."
                        ))

            if created_count:
                self.stdout.write(self.style.WARNING(f"Created {created_count} pick(s) for users with no submission."))

            # Iterate all picks (now includes newly created) for correctness + scoring + elimination logic
            picks = Pick.objects.filter(week=week).select_related(
                'user_profile', 'safe_pick', 'voted_out_pick', 'imty_challenge_winner_pick'
            )

            for pick in picks:
                profile = pick.user_profile

                # Correctness flags
                pick.safe_pick_correct = bool(pick.safe_pick and pick.safe_pick_id != voted_out_contestant.id)
                pick.voted_out_pick_correct = bool(pick.voted_out_pick and pick.voted_out_pick_id == voted_out_contestant.id)

                if pick.imty_challenge_winner_pick:
                    if n_tribes > 1 and winner_tribe:
                        pick.imty_challenge_winner_pick_correct = (
                            pick.imty_challenge_winner_pick.tribe == winner_tribe
                        )
                    else:
                        pick.imty_challenge_winner_pick_correct = (
                            imty_challenge_winner is not None and
                            pick.imty_challenge_winner_pick_id == imty_challenge_winner.id
                        )
                else:
                    pick.imty_challenge_winner_pick_correct = False

                # Check exile status BEFORE this week's pick (prevent double-trigger bug)
                was_exiled_before = profile.exiled
                was_eliminated_before = profile.eliminated
                
                # Safe=boot && no idol && week>1 && not permanently eliminated -> EXILE
                if (
                    pick.safe_pick_id == voted_out_contestant.id and
                    not pick.used_immunity_idol and
                    not was_exiled_before and  # Use captured state
                    not was_eliminated_before and  # Don't exile if already permanently eliminated
                    week.number > 1
                ):
                    profile.exiled = True
                    profile.save()
                    self.stdout.write(self.style.WARNING(
                        f"{profile.user.username} has been exiled (Safe pick went home; no idol)."
                    ))

                # Already EXILED and Safe hits boot again (no idol) -> permanent elimination
                elif (
                    was_exiled_before and  # Use captured state
                    not was_eliminated_before and  # Not already permanently eliminated
                    (pick.safe_pick_id == voted_out_contestant.id) and
                    (not pick.used_immunity_idol) and
                    week.number > 1
                ):
                    profile.eliminated = True  # Permanent elimination
                    profile.exiled = False  # Clear exile flag (they're now permanently out)
                    profile.save()
                    self.stdout.write(self.style.ERROR(
                        f"{profile.user.username} was already exiled and missed Safe again: ELIMINATED (permanent)."
                    ))

                # --- Points (idempotent) ---
                # Calculate base points BEFORE parlay logic (so correctness flags preserved for idol calc)
                base_safe = 1 if pick.safe_pick_correct else 0
                base_vo = 3 if pick.voted_out_pick_correct else 0
                base_im = 2 if pick.imty_challenge_winner_pick_correct else 0

                # ---------------------------
                #   PARLAY: all-or-nothing
                # ---------------------------
                # IMPORTANT: Don't modify correctness flags! They're needed for idol inventory calculation
                # Instead, set base points to 0 if parlay fails
                parlay_all_or_nothing = False
                if getattr(pick, 'parlay', False):
                    if not (pick.voted_out_pick_correct and pick.imty_challenge_winner_pick_correct):
                        parlay_all_or_nothing = True
                        # Zero out VO and Immunity points but preserve correctness flags
                        base_vo = 0
                        base_im = 0

                wv = getattr(pick, 'wager_voted_out', 0) or 0
                wi = getattr(pick, 'wager_immunity', 0) or 0

                if parlay_all_or_nothing:
                    wager_gain_vo = -wv
                    wager_gain_im = -wi
                    points_wagers = wager_gain_vo + wager_gain_im
                    parlay_bonus = 0
                else:
                    wager_gain_vo = (2 * wv) if pick.voted_out_pick_correct else -wv
                    wager_gain_im = int(1.5 * wi) if pick.imty_challenge_winner_pick_correct else -wi
                    points_wagers = wager_gain_vo + wager_gain_im
                    parlay_bonus = 0
                    if getattr(pick, 'parlay', False) and pick.voted_out_pick_correct and pick.imty_challenge_winner_pick_correct:
                        parlay_bonus = 20  # Huge bonus for hitting the ~0.3% parlay!

                pick.points_safe = base_safe
                pick.points_vo = base_vo
                pick.points_immunity = base_im
                pick.points_wagers = points_wagers
                pick.points_parlay = parlay_bonus
                pick.points_week_total = base_safe + base_vo + base_im + points_wagers + parlay_bonus

                pick.save()

            # --- Recompute aggregates (CURRENT_SEASON only) ---
            for prof in UserProfile.objects.filter(league=league):
                prof_picks = Pick.objects.filter(user_profile=prof, week__league=league, week__season=season)

                safe_correct = prof_picks.filter(safe_pick_correct=True).count()
                voted_correct = prof_picks.filter(voted_out_pick_correct=True).count()
                challenge_correct = prof_picks.filter(imty_challenge_winner_pick_correct=True).count()
                idols_used = prof_picks.filter(used_immunity_idol=True).count()
                picks_total = prof_picks.aggregate(s=Sum('points_week_total'))['s'] or 0

                prof.correct_guesses = safe_correct
                prof.correct_imty_challenge_guesses = challenge_correct
                prof.immunity_idols_played = idols_used
                prof.immunity_idols = max(0, voted_correct - idols_used)
                prof.total_score = picks_total - prof.exile_return_cost
                prof.save()

            self.stdout.write(self.style.SUCCESS(
                f"Week {week_number} processed for league '{league.name}' (Season {season})."
            ))