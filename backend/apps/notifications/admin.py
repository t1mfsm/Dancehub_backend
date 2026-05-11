from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'kind', 'user', 'course_id', 'lesson_id', 'read_at', 'created_at')
    list_filter = ('kind', 'read_at')
    search_fields = ('user__email', 'title', 'body')
    readonly_fields = ('created_at',)
    raw_id_fields = ('user', 'course', 'lesson')
