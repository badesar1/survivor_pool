from django.apps import AppConfig


class PoolappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'poolapp'

    def ready(self):
        import poolapp.signals