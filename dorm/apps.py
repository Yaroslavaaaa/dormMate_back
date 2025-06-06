from django.apps import AppConfig

class DormConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dorm'

    def ready(self):
        import dorm.signals




