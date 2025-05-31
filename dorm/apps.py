from django.apps import AppConfig

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dorm'




    def ready(self):
        from django.contrib.auth import get_user_model
        from django.db.utils import OperationalError, ProgrammingError
        import importlib

        try:
            User = get_user_model()
            dorm_models = importlib.import_module("dorm.models")
            Chat = dorm_models.Chat

            students = User.objects.filter(is_staff=False)

            for student in students:
                if not Chat.objects.filter(id=student.id).exists():
                    Chat.objects.create(id=student.id, student=student)
                    print(f"Чат создан: ID={student.id}, Студент={student.s}")
                else:
                    print(f"Чат уже существует: ID={student.id}")

        except (OperationalError, ProgrammingError, Exception) as e:
            print(f"Ошибка при автосоздании чатов: {e}")
