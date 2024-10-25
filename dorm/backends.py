from django.contrib.auth.backends import ModelBackend
from .models import User

class CustomBackend(ModelBackend):
    def authenticate(self, request, s=None, password=None, **kwargs):
        try:
            user = User.objects.get(s=s)
            if user.check_password(password):
                return user
            else:
                print(f"Password check failed for user: {user.s}")
        except User.DoesNotExist:
            print(f"User {s} does not exist")
            return None

