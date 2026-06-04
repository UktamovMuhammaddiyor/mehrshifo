from django.apps import AppConfig


class PagesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pages'

    def ready(self):
        from .knowledge.snapshot import connect_signals
        connect_signals()
