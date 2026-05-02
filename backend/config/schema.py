from drf_spectacular.extensions import OpenApiAuthenticationExtension


class OptionalJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "config.authentication.OptionalJWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
