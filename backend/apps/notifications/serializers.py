from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            'id',
            'kind',
            'title',
            'body',
            'course_id',
            'lesson_id',
            'read_at',
            'created_at',
        )
        read_only_fields = fields


class NotificationMarkReadSerializer(serializers.Serializer):
    read = serializers.BooleanField()
