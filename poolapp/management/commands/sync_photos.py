from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils.text import slugify
from pathlib import Path
from poolapp.models import Contestant

class Command(BaseCommand):
    help = "Sync Contestant.photo to files under MEDIA_ROOT/contestants/photos."

    def add_arguments(self, parser):
        parser.add_argument("--season-prefix", default="", help="Optional filename prefix, e.g. 's49_'")
        parser.add_argument("--dry", action="store_true", help="Dry-run only")

    def handle(self, *args, **opts):
        media_dir = Path(settings.MEDIA_ROOT) / "contestants" / "photos"
        prefix = opts["season-prefix"]

        if not media_dir.exists():
            self.stderr.write(f"Media dir not found: {media_dir}")
            return

        updated = 0
        for c in Contestant.objects.all():
            # Build a few candidate filenames from the name
            base = slugify(c.name).replace("-", "_")
            candidates = [
                f"{prefix}{base}.jpg",
                f"{prefix}{base}.jpeg",
                f"{prefix}{base}.png",
                f"{prefix}{base}.webp",
            ]

            found_rel = None
            for fname in candidates:
                if (media_dir / fname).exists():
                    found_rel = f"contestants/photos/{fname}"
                    break

            if found_rel and c.photo.name != found_rel:
                self.stdout.write(f"{c.name}: {c.photo.name or '∅'} -> {found_rel}")
                if not opts["dry"]:
                    # Assign the relative path (no file write; we’re just pointing at an existing file)
                    c.photo.name = found_rel
                    c.save(update_fields=["photo"])
                    updated += 1

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} contestant photo paths."))