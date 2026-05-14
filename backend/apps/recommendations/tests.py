from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from .services import _score_course_for_user


class RecommendationCityPreferenceTests(SimpleTestCase):
    def _build_course(self, *, city_id: int):
        course = SimpleNamespace(
            dance_style=SimpleNamespace(slug="bachata"),
            level="beginner",
            studio=SimpleNamespace(city_id=city_id),
            teacher_id=10,
            studio_id=20 + city_id,
            active_enrollments=0,
        )
        course.schedule_rows = MagicMock()
        course.schedule_rows.all.return_value = []
        return course

    def _build_profile(self):
        return SimpleNamespace(
            behavior_weight=0,
            preferred_styles_json=[{"key": "bachata", "weight": 1}],
            behavior_styles_json=[],
            teachers_json=[],
            studios_json=[],
            cities_json=[],
            preferred_weekdays_json=[],
            preferred_time_from=None,
            preferred_time_to=None,
            price_from=None,
            price_to=None,
            dance_level="beginner",
            city_id=1,
        )

    def test_same_city_course_scores_higher_than_other_city_course(self):
        user = SimpleNamespace()
        profile = self._build_profile()
        same_city_course = self._build_course(city_id=1)
        other_city_course = self._build_course(city_id=2)

        same_city_score, _, _ = _score_course_for_user(user, profile, same_city_course)
        other_city_score, _, _ = _score_course_for_user(user, profile, other_city_course)

        self.assertGreater(same_city_score, other_city_score)
