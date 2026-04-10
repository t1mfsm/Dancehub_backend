"""Статусы курса для витрины (по датам), не путать с полем Course.status в БД (draft/published/…)."""


class CourseLifecycleStatus:
    ACTIVE = "active"
    COMPLETED = "completed"
