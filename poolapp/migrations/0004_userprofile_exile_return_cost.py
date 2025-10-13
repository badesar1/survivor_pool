# Generated manually on 2025-10-13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("poolapp", "0003_pick_parlay_pick_points_immunity_pick_points_parlay_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="exile_return_cost",
            field=models.IntegerField(default=0),
        ),
    ]

