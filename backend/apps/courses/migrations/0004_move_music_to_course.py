from django.db import migrations, models


def move_music_to_course(apps, schema_editor):
    Course = apps.get_model('courses', 'Course')
    CourseMusic = apps.get_model('courses', 'CourseMusic')

    for music in CourseMusic.objects.all().iterator():
        Course.objects.filter(id=music.course_id).update(
            music_artist=music.artist or '',
            music_track=music.track or '',
            music_url=music.url or '',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0003_add_spots_left'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='music_artist',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='course',
            name='music_track',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='course',
            name='music_url',
            field=models.URLField(blank=True),
        ),
        migrations.RunPython(move_music_to_course, migrations.RunPython.noop),
        migrations.DeleteModel(
            name='CourseMusic',
        ),
    ]
