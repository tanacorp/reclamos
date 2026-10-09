from django.conf import settings


def empresa(request):
    return {
        "EMPRESA": settings.EMPRESA,
        "PLAZO_DIAS": settings.PLAZO_RESPUESTA_DIAS_HABILES,
    }
