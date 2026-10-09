from django.apps import AppConfig


class ReclamacionesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reclamaciones"

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_apply_config, sender=self)


def _apply_config(sender, **kwargs):
    try:
        from .models import Configuracion
        Configuracion.get().apply_to_django()
    except Exception:
        pass
