from apps.locations.models import City


def serialize_city(city: City) -> dict:
    return {
        "id": city.id,
        "name": city.name,
    }
