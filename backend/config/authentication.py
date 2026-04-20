from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


class OptionalJWTAuthentication(JWTAuthentication):
    """
    Как JWTAuthentication, но при невалидном/просроченном токене считает
    пользователя анонимным вместо ответа 401 (для публичных эндпоинтов с AllowAny).
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except InvalidToken:
            return None
