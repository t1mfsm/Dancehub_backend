from django.db import models


class UserRole(models.TextChoices):
    STUDENT = "student", "Student"
    TEACHER = "teacher", "Teacher"


class DanceLevel(models.TextChoices):
    BEGINNER = "beginner", "Beginner"
    INTERMEDIATE = "intermediate", "Intermediate"
    ADVANCED = "advanced", "Advanced"


class WeekdayCode(models.TextChoices):
    MON = "mon", "Monday"
    TUE = "tue", "Tuesday"
    WED = "wed", "Wednesday"
    THU = "thu", "Thursday"
    FRI = "fri", "Friday"
    SAT = "sat", "Saturday"
    SUN = "sun", "Sunday"


class CourseStatus(models.TextChoices):
    PUBLISHED = "published", "Published"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class LessonStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    CANCELLED = "cancelled", "Cancelled"


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    PENDING = "pending", "Pending"


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
