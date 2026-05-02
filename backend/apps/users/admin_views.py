from django.db import models


class UserFlagAdminView(models.Model):
    id = models.BigIntegerField(primary_key=True)
    user = models.ForeignKey("users.User", on_delete=models.DO_NOTHING, db_column="user_id")
    name = models.TextField()
    value = models.BooleanField()

    class Meta:
        managed = False
        db_table = "admin_user_flags_view"
        verbose_name = "Флаг пользователя"
        verbose_name_plural = "Флаги пользователей"


class UserSkillAdminView(models.Model):
    id = models.BigIntegerField(primary_key=True)
    user = models.ForeignKey("users.User", on_delete=models.DO_NOTHING, db_column="user_id")
    dance_style = models.ForeignKey("courses.DanceStyle", on_delete=models.DO_NOTHING, db_column="dance_style_id")
    level = models.TextField()

    class Meta:
        managed = False
        db_table = "admin_user_skills_view"
        verbose_name = "Навык пользователя"
        verbose_name_plural = "Навыки пользователей"


class FavoriteTeacherAdminView(models.Model):
    id = models.BigIntegerField(primary_key=True)
    user = models.ForeignKey("users.User", on_delete=models.DO_NOTHING, db_column="user_id")
    teacher = models.ForeignKey("users.TeacherProfile", on_delete=models.DO_NOTHING, db_column="teacher_id")

    class Meta:
        managed = False
        db_table = "admin_favorite_teachers_view"
        verbose_name = "Избранный преподаватель"
        verbose_name_plural = "Избранные преподаватели"
