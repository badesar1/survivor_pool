from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.core.files import File
from django.conf import settings
from django.utils import timezone

from poolapp.models import Contestant, League, Week

from zoneinfo import ZoneInfo
from io import BytesIO
import datetime
import json
import os
import requests

class Command(BaseCommand):
    help = (
        "Initialize (or update) contestants for a given season from a JSON file and "
        "optionally create the season's Week rows for all leagues. Idempotent; no deletes."
    )

    def add_arguments(self, parser):
        parser.add_argument('--season', type=int, required=True, help='Season number, e.g. 49')
        parser.add_argument('--json', type=str, required=True, help='Path to contestants JSON')
        parser.add_argument('--download-photos', action='store_true', help='Download and attach photos')
        parser.add_argument('--overwrite-photos', action='store_true', help='Re-download even if a photo exists')
        parser.add_argument('--create-weeks', action='store_true', help='Create Week rows for all leagues for this season')
        # Week creation config (falls back to settings.SEASON_CONFIG if present)
        parser.add_argument('--start-date', type=str, help='YYYY-MM-DD season start date (overrides settings)')
        parser.add_argument('--episodes', type=int, help='How many episodes/weeks to create (overrides settings)')
        parser.add_argument('--lock-hour-et', type=int, help='Lock hour in ET (default from settings; often 20)')
        parser.add_argument('--lock-weekday', type=int, help='0=Mon..6=Sun (default from settings; often 2=Wed)')

    def handle(self, *args, **opts):
        season = opts['season']
        json_path = opts['json']
        dl_photos = opts['download_photos']
        overwrite = opts['overwrite_photos']
        do_weeks = opts['create_weeks']

        # ---------- Load JSON ----------
        if not os.path.exists(json_path):
            raise CommandError(f"JSON not found: {json_path}")
        with open(json_path, 'r') as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise CommandError("Contestants JSON must be a list of objects.")

        # ---------- Ensure media directory exists (prod-safe) ----------
        # Your prod path: /opt/render/project/src/media/contestants/photos
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if not media_root:
            raise CommandError("settings.MEDIA_ROOT is not set.")
        photos_dir = os.path.join(media_root, 'contestants', 'photos')
        os.makedirs(photos_dir, exist_ok=True)

        # ---------- Create/Update Contestants ----------
        created, updated, photos_ok, photos_fail = 0, 0, 0, 0

        for c in data:
            name = c.get('name')
            if not name:
                self.stderr.write("Skipping row with no 'name'.")
                continue

            bio_parts = []
            if c.get('age'): bio_parts.append(f"{c['age']} years old")
            if c.get('hometown'): bio_parts.append(c['hometown'])
            if c.get('occupation'): bio_parts.append(c['occupation'])
            bio_text = " ".join(bio_parts) if bio_parts else "Bio not provided."

            defaults = {
                'bio': bio_text,
                'tribe': c.get('tribe'),
                'bio_link': c.get('bioLink'),
                'is_active': True,
            }

            obj, was_created = Contestant.objects.get_or_create(
                season=season, name=name, defaults=defaults
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"[S{season}] Created: {name}"))
            else:
                for k, v in defaults.items():
                    setattr(obj, k, v)
                obj.save()
                updated += 1
                self.stdout.write(f"[S{season}] Updated: {name}")

            # --- Download photo if requested ---
            photo_url = c.get('photoLink')
            if dl_photos and photo_url:
                need_photo = overwrite
                # If not overwriting, attach only if empty or default placeholder
                if not overwrite:
                    if not obj.photo or not obj.photo.name or obj.photo.name.startswith('default_images/'):
                        need_photo = True

                if need_photo:
                    try:
                        r = requests.get(photo_url, timeout=15)
                        r.raise_for_status()
                        # Decide a clean filename; Django will put it under upload_to dir automatically
                        ext = photo_url.split('?')[0].split('.')[-1].lower()
                        if len(ext) > 5 or '/' in ext or '.' in ext and ext not in ('jpg','jpeg','png','gif','webp'):
                            ext = 'jpg'
                        fname = f"S{season}_{name.replace(' ', '_')}.{ext}"

                        # Save via ImageField to ensure correct MEDIA_ROOT usage in prod
                        obj.photo.save(fname, ContentFile(r.content), save=True)
                        photos_ok += 1
                        self.stdout.write(self.style.SUCCESS(f"[S{season}] Photo saved: {name} -> {obj.photo.name}"))
                    except Exception as e:
                        photos_fail += 1
                        self.stderr.write(f"[S{season}] Photo failed for {name}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"S{season} contestants complete. Created={created}, Updated={updated}, "
            f"Photos OK={photos_ok}, Photos Fail={photos_fail}"
        ))

        # ---------- Create Weeks (idempotent, season-scoped) ----------
        if do_weeks:
            cfg = getattr(settings, 'SEASON_CONFIG', {}).get(season, {})
            # Resolve config from flags or settings
            if opts.get('start_date'):
                start_date = datetime.date.fromisoformat(opts['start_date'])
            else:
                start_date = cfg.get('START_DATE') or getattr(settings, 'SEASON_START_DATE', None)
                if not isinstance(start_date, datetime.date):
                    raise CommandError("Start date not provided and not found in settings.SEASON_CONFIG or SEASON_START_DATE.")

            episodes = opts.get('episodes') or cfg.get('EPISODES') or 13
            lock_hour = opts.get('lock_hour_et') if opts.get('lock_hour_et') is not None else cfg.get('LOCK_HOUR_ET', 20)
            lock_weekday = opts.get('lock_weekday') if opts.get('lock_weekday') is not None else cfg.get('LOCK_WEEKDAY', 2)  # 2=Wed
            eastern = ZoneInfo("America/New_York")

            leagues = League.objects.all()
            total_created = 0
            for league in leagues:
                created_count = 0
                # If this league already has any Week rows for this season, we *ensure* all weeks exist (idempotent)
                for n in range(1, episodes + 1):
                    wk_start = start_date + datetime.timedelta(weeks=n - 1)
                    days_to_target = (lock_weekday - wk_start.weekday()) % 7
                    lock_date = wk_start + datetime.timedelta(days=days_to_target)
                    naive_lock = datetime.datetime(
                        lock_date.year, lock_date.month, lock_date.day,
                        int(lock_hour), 0, 0, 0
                    )
                    lock_dt = timezone.make_aware(naive_lock, eastern)

                    _, was_created = Week.objects.get_or_create(
                        league=league,
                        season=season,
                        number=n,
                        defaults={'start_date': wk_start, 'lock_time': lock_dt}
                    )
                    if was_created:
                        created_count += 1
                total_created += created_count
                self.stdout.write(self.style.SUCCESS(
                    f"[{league.name}] S{season}: ensured {episodes} week(s), created {created_count} new."
                ))

            self.stdout.write(self.style.SUCCESS(
                f"Week creation complete for S{season}. Total new weeks created across all leagues: {total_created}"
            ))