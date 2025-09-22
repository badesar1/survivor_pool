# poolapp/management/commands/sync_photos.py
from django.core.management.base import BaseCommand
from django.conf import settings
from pathlib import Path
from poolapp.models import Contestant


class Command(BaseCommand):
    help = "Sync Contestant.photo fields to files in media/contestants/photos (expects First_Last.jpg)."

    def handle(self, *args, **options):
        media_dir = Path(settings.MEDIA_ROOT) / "contestants" / "photos"
        if not media_dir.exists():
            self.stderr.write(f"Media directory not found: {media_dir}")
            return

        updated = 0
        for c in Contestant.objects.all():
            # Expect "First Last" → "First_Last.jpg"
            candidate = f"{c.name.replace(' ', '_')}.jpg"
            candidate_path = media_dir / candidate
            if candidate_path.exists():
                rel_path = f"contestants/photos/{candidate}"
                if c.photo.name != rel_path:
                    c.photo.name = rel_path
                    c.save(update_fields=["photo"])
                    self.stdout.write(f"Updated {c.name} -> {rel_path}")
                    updated += 1
            else:
                self.stdout.write(f"No photo found for {c.name} (expected {candidate})")

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} contestant photo paths."))