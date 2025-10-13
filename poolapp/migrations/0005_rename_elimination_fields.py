# Generated manually on 2025-10-13

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("poolapp", "0004_userprofile_exile_return_cost"),
    ]

    operations = [
        # Rename eliminated -> exiled (temporary state)
        migrations.RenameField(
            model_name="userprofile",
            old_name="eliminated",
            new_name="exiled",
        ),
        # Rename has_returned -> eliminated (permanent state)
        migrations.RenameField(
            model_name="userprofile",
            old_name="has_returned",
            new_name="eliminated",
        ),
    ]

