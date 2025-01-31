# poolapp/management/commands/startup_setup.py

from django.core.management.base import BaseCommand
from django.core.files import File
from django.utils import timezone
from poolapp.models import Contestant, Week
import datetime
from zoneinfo import ZoneInfo
import os
from django.conf import settings
import json
import requests
from io import BytesIO

# Define the season start date
SEASON_START_DATE = settings.SEASON_START_DATE  # Sunday, Dec 8, 2024

class Command(BaseCommand):
    help = "Set up initial contestants and the first week of the show."

    def handle(self, *args, **options):
        self.stdout.write("Starting startup setup...")

        # Path to contestant photos
        media_root = os.path.join(os.getcwd(), 'media')
        photos_dir = os.path.join(media_root, 'contestants', 'photos')

        # Define contestants data
        with open(os.path.join(media_root, 'contestants', "s48_contestants.json"), "r") as file:
            contestants_data = json.load(file)

        # Ensure the photos directory exists
        if not os.path.exists(photos_dir):
            self.stderr.write(f"Photos directory does not exist: {photos_dir}")
            return

        # Create Contestants
        for c_data in contestants_data:
            name = c_data.get("name")
            age = c_data.get("age")
            hometown = c_data.get("hometown")
            occupation = c_data.get("occupation")
            tribe = c_data.get("tribe")
            bio_link = c_data.get("bioLink")
            photo_url = c_data.get("photoLink")
            bio_parts = []
            if age:
                bio_parts.append(f"{age} years old")
            if hometown:
                bio_parts.append(f"{hometown}")
            if occupation:
                bio_parts.append(f"{occupation}")
            bio_text = ", ".join(bio_parts)
 
            contestant, created = Contestant.objects.get_or_create(
                name=c_data['name'],
                defaults={
                    'bio': bio_text,
                    'tribe': tribe,
                    'bio_link': bio_link,
                },
            )
            if created:
                self.stdout.write(f"Created contestant: {contestant.name}")
            else:
                # If contestant already exists, optionally update fields
                contestant.bio = bio_text
                contestant.tribe = tribe
                contestant.bio_link = bio_link
                contestant.save()
                self.stdout.write(f"Updated contestant: {contestant.name}")

            # If photo URL is provided, try to download it
            if photo_url:
                try:
                    response = requests.get(photo_url, timeout=10)
                    if response.status_code == 200:
                        # Derive a filename (e.g., from the name or from the URL)
                        extension = photo_url.split('.')[-1]
                        if len(extension) > 5:
                            # Fallback if extension is weird
                            extension = "jpg"
                        file_name = f"{name.replace(' ', '_')}.{extension}"

                        # Save image to ImageField
                        img_content = BytesIO(response.content)
                        contestant.photo.save(file_name, File(img_content), save=True)
                        self.stdout.write(f"Downloaded and assigned photo for {contestant.name}")
                    else:
                        self.stderr.write(f"Failed to download photo for {contestant.name}: Status {response.status_code}")
                except requests.RequestException as e:
                    self.stderr.write(f"Error downloading photo for {contestant.name}: {e}")

        self.stdout.write(self.style.SUCCESS("Startup setup complete!"))