# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="spots_left",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
