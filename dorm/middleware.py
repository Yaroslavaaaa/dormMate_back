# core/middleware.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model
from .models import Admin

class JWTAuthMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()

    def __call__(self, request):
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

    def process_request(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            request.auditlog_ignore = True
            return

        is_my_admin = Admin.objects.filter(user_ptr_id=user.pk).exists()
        if not (user.is_superuser or is_my_admin):
            request.auditlog_ignore = True