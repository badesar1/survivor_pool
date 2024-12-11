# poolapp/management/commands/startup_setup.py

from django.core.management.base import BaseCommand
from django.core.files import File
from django.utils import timezone
from poolapp.models import Contestant, Week
import datetime
from zoneinfo import ZoneInfo
import os
from django.conf import settings

# Define the season start date
SEASON_START_DATE = datetime.date(2024, 12, 8)  # Sunday, Dec 8, 2024

class Command(BaseCommand):
    help = "Set up initial contestants and the first week of the show."

    def handle(self, *args, **options):
        self.stdout.write("Starting startup setup...")

        # Define contestants data
        contestants_data = [
            {
                'name': 'Alice Johnson',
                'bio': 'A fearless adventurer from the Rockies.',
                'photo_filename': 'Unknown1.jpeg'
            },
            {
                'name': 'Bob Smith',
                'bio': 'A strategic mastermind with a background in chess.',
                'photo_filename': 'Unknown2.jpeg'
            },
            {
                'name': 'Charlie Lee',
                'bio': 'An outdoor enthusiast and survival expert.',
                'photo_filename': 'Unknown3.jpeg'
            },
            {
                'name': 'Dog',
                'bio': 'A dog.',
                'photo_filename': 'Unknown4.jpeg'
            },
            {
                'name': 'Ben',
                'bio': 'A fearless adventurer from the Rockies.',
                'photo_filename': 'Unknown1.jpeg'
            },
            {
                'name': 'James',
                'bio': 'A strategic mastermind with a background in chess.',
                'photo_filename': 'Unknown2.jpeg'
            },
            {
                'name': 'Bret',
                'bio': 'An outdoor enthusiast and survival expert.',
                'photo_filename': 'Unknown3.jpeg'
            },
            {
                'name': 'Rob',
                'bio': 'A dog.',
                'photo_filename': 'Unknown4.jpeg'
            },
            {
                'name': 'test1',
                'bio': 'A fearless adventurer from the Rockies.',
                'photo_filename': 'Unknown1.jpeg'
            },
            {
                'name': 'test2',
                'bio': 'A strategic mastermind with a background in chess.',
                'photo_filename': 'Unknown2.jpeg'
            },
            {
                'name': 'test3',
                'bio': 'An outdoor enthusiast and survival expert.',
                'photo_filename': 'Unknown3.jpeg'
            },
            {
                'name': 'test4',
                'bio': 'A dog.',
                'photo_filename': 'Unknown4.jpeg'
            },
            # Add more contestants as needed
        ]

        # Path to contestant photos
        media_root = os.path.join(os.getcwd(), 'media')
        photos_dir = os.path.join(media_root, 'contestants', 'photos')

        # Ensure the photos directory exists
        if not os.path.exists(photos_dir):
            self.stderr.write(f"Photos directory does not exist: {photos_dir}")
            return

        # Create Contestants
        for c_data in contestants_data:
            contestant, created = Contestant.objects.get_or_create(
                name=c_data['name'],
                defaults={
                    'bio': c_data['bio']
                }
            )
            if created:
                self.stdout.write(f"Created contestant: {contestant.name}")
                # Assign photo
                photo_path = os.path.join(photos_dir, c_data['photo_filename'])
                if os.path.isfile(photo_path):
                    with open(photo_path, 'rb') as img_file:
                        contestant.photo.save(c_data['photo_filename'], File(img_file), save=True)
                    self.stdout.write(f"Assigned photo to {contestant.name}")
                else:
                    self.stderr.write(f"Photo file not found for {contestant.name}: {photo_path}")
            else:
                self.stdout.write(f"Contestant already exists: {contestant.name}")

        self.stdout.write(self.style.SUCCESS("Startup setup complete!"))