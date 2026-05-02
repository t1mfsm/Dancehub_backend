from django.db import models


class FavoriteCourseAdminView(models.Model):
    id = models.BigIntegerField(primary_key=True)
    user = models.ForeignKey("users.User", on_delete=models.DO_NOTHING, db_column="user_id")
    course = models.ForeignKey("courses.Course", on_delete=models.DO_NOTHING, db_column="course_id")

    class Meta:
        managed = False
        db_table = "admin_favorite_courses_view"
        verbose_name = "Избранный курс"
        verbose_name_plural = "Избранные курсы"
