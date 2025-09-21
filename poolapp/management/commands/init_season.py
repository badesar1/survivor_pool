# poolapp/management/commands/init_season.py
from django.core.management.base import BaseCommand, CommandError
from django.core.files import File
from poolapp.models import Contestant
from io import BytesIO
import json, requests, os

class Command(BaseCommand):
    help = "Idempotently create/update contestants for a given season from JSON (no deletes)."

    def add_arguments(self, parser):
        parser.add_argument('--season', type=int, required=True)
        parser.add_argument('--json', type=str, required=True)
        parser.add_argument('--download-photos', action='store_true')

    def handle(self, *args, **opts):
        season = opts['season']
        path = opts['json']
        if not os.path.exists(path):
            raise CommandError(f"JSON not found: {path}")
        with open(path, 'r') as f:
            data = json.load(f)

        created, updated = 0, 0
        for c in data:
            name = c.get('name')
            if not name: continue
            defaults = {
                'bio': " ".join(filter(None, [
                    f"{c.get('age')} years old" if c.get('age') else None,
                    c.get('hometown'),
                    c.get('occupation'),
                ])),
                'tribe': c.get('tribe'),
                'bio_link': c.get('bioLink'),
                'is_active': True,
            }
            obj, was_created = Contestant.objects.get_or_create(
                season=season, name=name, defaults=defaults
            )
            if not was_created:
                for k, v in defaults.items(): setattr(obj, k, v)
                obj.save(); updated += 1
            else:
                created += 1

            if opts['download_photos'] and c.get('photoLink'):
                url = c['photoLink']
                try:
                    r = requests.get(url, timeout=10); r.raise_for_status()
                    ext = url.split('?')[0].split('.')[-1]
                    if len(ext) > 5: ext = 'jpg'
                    fname = f"S{season}_{name.replace(' ', '_')}.{ext}"
                    obj.photo.save(fname, File(BytesIO(r.content)), save=True)
                except Exception as e:
                    self.stderr.write(f"Photo failed for {name}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"S{season} contestants ready. Created={created}, Updated={updated}."
        ))