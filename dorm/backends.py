from django.contrib.auth.backends import ModelBackend
from .models import User

class CustomBackend(ModelBackend):
    def authenticate(self, request, s=None, password=None, **kwargs):
        try:
            user = User.objects.get(s=s)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

