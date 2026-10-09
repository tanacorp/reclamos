import base64
import io

import qrcode
from django.contrib import admin
from django.utils.html import format_html

from .models import Feriado, Reclamo, Sala, Seguimiento


def _qr_base64(url: str) -> str:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "distrito", "email_notificacion", "activa", "ver_qr")
    list_filter = ("activa",)
    search_fields = ("nombre", "codigo", "direccion")
    readonly_fields = ("qr_hoja",)

    def _url_hoja(self, request, obj):
        return request.build_absolute_uri(obj.get_absolute_url())

    @admin.display(description="QR hoja de reclamación")
    def qr_hoja(self, obj):
        if not obj.pk:
            return "Guarde la sala primero para generar el QR."
        from django.urls import reverse
        from django.conf import settings
        path = reverse("reclamaciones:hoja", args=[obj.codigo])
        host = getattr(settings, "SITE_URL", "").rstrip("/")
        if not host:
            allowed = [h for h in settings.ALLOWED_HOSTS if h not in ("*", "")]
            if allowed:
                host = allowed[0]
                scheme = "https" if not settings.DEBUG else "http"
                host = f"{scheme}://{host}"
            else:
                host = "http://localhost:8000"
        url = f"{host}{path}"
        data = _qr_base64(url)
        return format_html(
            '<img src="data:image/png;base64,{}" width="180" height="180" alt="QR {}"><br>'
            '<small style="word-break:break-all">{}</small>',
            data, obj.nombre, url,
        )

    @admin.display(description="QR")
    def ver_qr(self, obj):
        from django.urls import reverse as r
        url = r("admin:reclamaciones_sala_change", args=[obj.pk])
        return format_html('<a href="{}">Ver QR</a>', url)

    def get_fieldsets(self, request, obj=None):
        base = [
            (None, {"fields": ("codigo", "nombre", "direccion", "distrito", "email_notificacion", "activa")}),
        ]
        if obj and obj.pk:
            base.append(("QR para imprimir / pegar en el local", {"fields": ("qr_hoja",)}))
        return base


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "descripcion")
    date_hierarchy = "fecha"


class SeguimientoInline(admin.TabularInline):
    model = Seguimiento
    extra = 0
    readonly_fields = ("fecha", "usuario", "estado", "nota")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Reclamo)
class ReclamoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "sala", "tipo", "estado", "nombre_completo", "fecha_registro", "fecha_limite")
    list_filter = ("sala", "estado", "tipo")
    search_fields = ("codigo", "nombres", "apellidos", "numero_documento", "email")
    readonly_fields = ("codigo", "fecha_registro", "ip_origen")
    inlines = [SeguimientoInline]
    date_hierarchy = "fecha_registro"

    def has_delete_permission(self, request, obj=None):
        return False
