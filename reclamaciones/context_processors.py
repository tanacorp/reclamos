from django.conf import settings


def empresa(request):
    """
    En multi-empresa no hay una empresa "global".
    Exponemos solo el plazo por defecto y un nombre genérico para el título del panel.
    Cada vista pasa su propia empresa al template cuando la necesita.
    """
    try:
        from .models import Empresa
        primera = Empresa.objects.order_by("pk").first()
        emp = {
            "razon_social": primera.razon_social if primera else "",
            "nombre_comercial": primera.nombre_comercial if primera else "Libro de Reclamaciones",
            "ruc": primera.ruc if primera else "",
            "domicilio_fiscal": primera.domicilio_fiscal if primera else "",
        }
        plazo = primera.plazo_dias_habiles if primera else getattr(settings, "PLAZO_RESPUESTA_DIAS_HABILES", 15)
    except Exception:
        emp = getattr(settings, "EMPRESA", {"nombre_comercial": "Libro de Reclamaciones"})
        plazo = getattr(settings, "PLAZO_RESPUESTA_DIAS_HABILES", 15)
    return {"EMPRESA": emp, "PLAZO_DIAS": plazo}
