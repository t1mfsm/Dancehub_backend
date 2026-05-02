from datetime import datetime, timezone

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions

from apps.users.models import User


def build_tokens_for_user(user: User) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    access_payload = {
        "sub": user.id,
        "type": "access",
        "iat": now,
        "exp": now + settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
    }
    refresh_payload = {
        "sub": user.id,
        "type": "refresh",
        "iat": now,
        "exp": now + settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"],
    }
    return {
        "access": jwt.encode(access_payload, settings.SECRET_KEY, algorithm="HS256"),
        "refresh": jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm="HS256"),
    }


def decode_token(token: str, expected_type: str | None = None) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise exceptions.AuthenticationFailed("Invalid token.") from exc
    if expected_type and payload.get("type") != expected_type:
        raise exceptions.AuthenticationFailed("Invalid token type.")
    return payload


class OptionalJWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        payload = decode_token(parts[1], expected_type="access")
        user_id = payload.get("sub")
        if not user_id:
            raise exceptions.AuthenticationFailed("Invalid token payload.")
        user = User.objects.filter(id=user_id).select_related("city").first()
        if user is None:
            raise exceptions.AuthenticationFailed("User not found.")
        return user, payload
