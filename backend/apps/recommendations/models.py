from django.db import models


class CourseView(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="course_views", db_column="user_id")
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="course_views", db_column="course_id")
    viewed_at = models.DateTimeField()
    source = models.TextField(default="course_page")

    class Meta:
        db_table = "course_views"
        managed = False
        ordering = ["-viewed_at", "-id"]


class UserRecommendationProfile(models.Model):
    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="recommendation_profile",
        db_column="user_id",
        primary_key=True,
    )
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recommendation_profiles",
        db_column="city_id",
    )
    dance_level = models.TextField(null=True, blank=True)
    preferred_styles_json = models.JSONField(default=list, blank=True)
    preferred_weekdays_json = models.JSONField(default=list, blank=True)
    preferred_time_from = models.TimeField(null=True, blank=True)
    preferred_time_to = models.TimeField(null=True, blank=True)
    price_from = models.IntegerField(null=True, blank=True)
    price_to = models.IntegerField(null=True, blank=True)
    behavior_styles_json = models.JSONField(default=list, blank=True)
    teachers_json = models.JSONField(default=list, blank=True)
    studios_json = models.JSONField(default=list, blank=True)
    cities_json = models.JSONField(default=list, blank=True)
    behavior_weight = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    last_event_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "user_recommendation_profiles"
        managed = False


class UserCourseRecommendation(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="course_recommendations",
        db_column="user_id",
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="recommended_to_users",
        db_column="course_id",
    )
    score = models.DecimalField(max_digits=8, decimal_places=4)
    reasons_json = models.JSONField(default=list, blank=True)
    factors_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField()

    class Meta:
        db_table = "user_course_recommendations"
        managed = False
        ordering = ["-score", "-computed_at", "-id"]

