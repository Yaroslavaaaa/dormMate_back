# core/middleware.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model
from .models import Admin

class JWTAuthMiddleware:
    """
    Достаёт JWT-токен из заголовка Authorization
    и сразу ставит request.user = валидный пользователь.
    Запускается ДО AuditlogMiddleware, чтобы тот видел уже аутентифицированного user.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()

    def __call__(self, request):
        # попытаемся достать токен
        header = self.jwt_auth.get_header(request)
        if header is not None:
            raw_token = self.jwt_auth.get_raw_token(header)
            if raw_token is not None:
                try:
                    validated_token = self.jwt_auth.get_validated_token(raw_token)
                    user = self.jwt_auth.get_user(validated_token)
                    request.user = user
                except Exception:
                    request.user = AnonymousUser()
        return self.get_response(request)



User = get_user_model()

class AuditLogRestrictMiddleware(MiddlewareMixin):
    """
    Далеко после AuditlogMiddleware: если request.user не админ из вашей
    таблицы Admin и не is_superuser, ставим флаг ignore — и auditlog ничего не сохранит.
    """
    def process_request(self, request):
        user = getattr(request, 'user', None)
        # если нет пользователя (например, anonymous) — игнорим
        if not user or not user.is_authenticated:
            request.auditlog_ignore = True
            return

        # проверяем: или django-суперюзер, или ваша модель Admin
        is_my_admin = Admin.objects.filter(user_ptr_id=user.pk).exists()
        if not (user.is_superuser or is_my_admin):
            request.auditlog_ignore = True