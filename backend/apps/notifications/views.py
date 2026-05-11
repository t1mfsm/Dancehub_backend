from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationMarkReadSerializer, NotificationSerializer
from apps.notifications.services import maybe_send_lesson_reminders


@extend_schema_view(
    get=extend_schema(
        tags=['Notifications'],
        summary='Мои уведомления',
        description='Список уведомлений текущего пользователя (новые сверху).',
    ),
)
class NotificationListAPIView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def list(self, request, *args, **kwargs):
        maybe_send_lesson_reminders()
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')


@extend_schema(
    tags=['Notifications'],
    summary='Отметить все уведомления прочитанными',
)
class NotificationReadAllAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        now = timezone.now()
        updated = Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=now)
        return Response({'marked': updated}, status=status.HTTP_200_OK)


@extend_schema_view(
    patch=extend_schema(
        tags=['Notifications'],
        summary='Обновить уведомление',
        description='Отметить как прочитанное / непрочитанное.',
        request=NotificationMarkReadSerializer,
    ),
)
class NotificationDetailAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def patch(self, request, *args, **kwargs):
        notification = self.get_object()
        body = NotificationMarkReadSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if body.validated_data['read']:
            notification.read_at = timezone.now()
        else:
            notification.read_at = None
        notification.save(update_fields=['read_at'])
        return Response(NotificationSerializer(notification).data)
