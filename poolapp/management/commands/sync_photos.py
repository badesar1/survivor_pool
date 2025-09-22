# poolapp/management/commands/sync_photos.py
from django.core.management.base import BaseCommand
from django.conf import settings
from pathlib import Path
from django.utils.text import slugify
from poolapp.models import Contestant


class Command(BaseCommand):
    help = "Sync Contestant.photo fields to existing files in media/contestants/photos."

    def handle(self, *args, **options):
        media_dir = Path(settings.MEDIA_ROOT) / "contestants" / "photos"
        if not media_dir.exists():
            self.stderr.write(f"Media directory not found: {media_dir}")
            return

        updated = 0
        for c in Contestant.objects.all():
            slug = slugify(c.name).replace("-", "_")
            candidates = [
                f"{slug}.jpg",
                f"{slug}.jpeg",
                f"{slug}.png",
            ]

            found_rel = None
            for fname in candidates:
                if (media_dir / fname).exists():
                    found_rel = f"contestants/photos/{fname}"
                    break

            if found_rel:
                if c.photo.name != found_rel:
                    c.photo.name = found_rel
                    c.save(update_fields=["photo"])
                    self.stdout.write(f"Updated {c.name} -> {found_rel}")
                    updated += 1
            else:
                self.stdout.write(f"No photo found for {c.name} (looked for {candidates})")

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} contestant photo paths."))