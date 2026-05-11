from django.urls import path

from apps.notifications.views import (
    NotificationDetailAPIView,
    NotificationListAPIView,
    NotificationReadAllAPIView,
)

app_name = 'notifications'

urlpatterns = [
    path('notifications/', NotificationListAPIView.as_view(), name='notification-list'),
    path(
        'notifications/read-all/',
        NotificationReadAllAPIView.as_view(),
        name='notification-read-all',
    ),
    path(
        'notifications/<int:pk>/',
        NotificationDetailAPIView.as_view(),
        name='notification-detail',
    ),
]
