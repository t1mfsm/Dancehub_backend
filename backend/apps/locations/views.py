from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from .models import City
from .serializers import CitySerializer


@extend_schema_view(
    get=extend_schema(
        tags=["Reference"],
        summary="Список городов",
        description="Возвращает справочник городов для фильтров и форм.",
    )
)
class CityListAPIView(generics.ListAPIView):
    queryset = City.objects.all().order_by("name")
    serializer_class = CitySerializer
