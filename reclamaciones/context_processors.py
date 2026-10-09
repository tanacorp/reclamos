from django.conf import settings


def empresa(request):
    # EMPRESA en settings solo se usa como fallback en desarrollo
    return {
        "EMPRESA": getattr(settings, "EMPRESA", {}),
        "PLAZO_DIAS": getattr(settings, "PLAZO_RESPUESTA_DIAS_HABILES", 15),
    }
