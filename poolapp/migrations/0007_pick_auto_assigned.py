from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("poolapp", "0006_contestant_season_week_season_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pick",
            name="auto_assigned",
            field=models.BooleanField(default=False),
        ),
    ]


