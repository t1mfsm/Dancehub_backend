from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_user_middle_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacherprofile",
            name="images",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
