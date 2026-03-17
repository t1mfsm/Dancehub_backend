from django.urls import path

from .views import CityListAPIView


app_name = "locations"

urlpatterns = [
    path("cities/", CityListAPIView.as_view(), name="city-list"),
]
