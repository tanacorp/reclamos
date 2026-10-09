from django.core.management.base import BaseCommand

from reclamaciones.models import Sala


class Command(BaseCommand):
    help = "Crea salas de ejemplo para probar el libro de reclamaciones."

    def handle(self, *args, **options):
        datos = [
            ("MIR", "Sala Miraflores", "Av. Ejemplo 123", "Miraflores"),
            ("SMP", "Sala San Martín de Porres", "Av. Ejemplo 456", "San Martín de Porres"),
            ("CHO", "Sala Chorrillos", "Av. Ejemplo 789", "Chorrillos"),
        ]
        for codigo, nombre, direccion, distrito in datos:
            _, creada = Sala.objects.get_or_create(
                codigo=codigo, defaults={"nombre": nombre, "direccion": direccion, "distrito": distrito}
            )
            self.stdout.write(f"{'Creada' if creada else 'Ya existe'}: {nombre}")
