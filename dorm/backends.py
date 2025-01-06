from django.contrib.auth.backends import ModelBackend
from .models import User

class CustomBackend(ModelBackend):
    def authenticate(self, request, s=None, phone_number=None, password=None, **kwargs):
        try:
            if s:
                user = User.objects.get(s=s)
            elif phone_number:
                user = User.objects.get(phone_number=phone_number)
            else:
                return None

            if user.check_password(password):
                return user
            else:
                print(f"Password check failed for user: {user.s or user.phone_number}")
        except User.DoesNotExist:
            print(f"User {s or phone_number} does not exist")
            return None
