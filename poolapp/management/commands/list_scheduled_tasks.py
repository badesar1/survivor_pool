# poolapp/management/commands/list_scheduled_tasks.py
from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask

class Command(BaseCommand):
    help = 'List all scheduled tasks'

    def handle(self, *args, **options):
        tasks = PeriodicTask.objects.all()
        for task in tasks:
            self.stdout.write(f"{task.name} scheduled for {task.clocked.clocked_time if task.clocked else 'N/A'}")