from rest_framework.response import Response
from rest_framework.views import APIView

from .models import City
from .serializers import serialize_city


class CityListAPIView(APIView):
    def get(self, _request):
        cities = City.objects.all().order_by("name")
        return Response([serialize_city(city) for city in cities])
