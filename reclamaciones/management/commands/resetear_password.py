import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Resetea la contraseña del superusuario desde variables de entorno."

    def handle(self, *args, **kwargs):
        User = get_user_model()
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

        if not password:
            self.stdout.write("DJANGO_SUPERUSER_PASSWORD no definida, se omite.")
            return

        try:
            user = User.objects.get(username=username)
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Contraseña de '{username}' actualizada."))
        except User.DoesNotExist:
            self.stdout.write(f"Usuario '{username}' no encontrado.")
