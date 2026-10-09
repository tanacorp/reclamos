import csv
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .forms import (
    ConfiguracionForm, ConsultaForm, FeriadoForm, FiltroReclamosForm,
    GestionForm, HojaReclamacionForm, SalaForm, UsuarioForm,
)
from .models import Configuracion, Feriado, Reclamo, Sala, Seguimiento

logger = logging.getLogger(__name__)

SIGNING_SALT = "reclamaciones.constancia"


def _ip(request):
    return request.META.get("REMOTE_ADDR")


def _enviar(asunto, cuerpo, destinatarios):
    destinatarios = [d for d in destinatarios if d]
    if not destinatarios:
        return
    try:
        send_mail(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, destinatarios, fail_silently=False)
    except Exception:
        logger.exception("No se pudo enviar el correo '%s'", asunto)


# ---------------------------------------------------------------- Front público

class HojaReclamacionView(View):
    template_name = "reclamaciones/hoja.html"

    def _sala(self, codigo):
        return get_object_or_404(Sala, codigo__iexact=codigo, activa=True)

    def get(self, request, sala_codigo):
        sala = self._sala(sala_codigo)
        return render(request, self.template_name, {"sala": sala, "form": HojaReclamacionForm()})

    def post(self, request, sala_codigo):
        sala = self._sala(sala_codigo)
        form = HojaReclamacionForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                reclamo = form.save(commit=False)
                reclamo.sala = sala
                reclamo.ip_origen = _ip(request)
                reclamo.save()
                Seguimiento.objects.create(
                    reclamo=reclamo, estado=reclamo.estado, nota="Hoja de reclamación registrada por el consumidor."
                )
            self._notificar(request, reclamo)
            token = signing.dumps(reclamo.codigo, salt=SIGNING_SALT)
            return redirect("reclamaciones:constancia", token=token)
        return render(request, self.template_name, {"sala": sala, "form": form}, status=400)

    def _notificar(self, request, reclamo):
        cuerpo = render_to_string("reclamaciones/email_constancia.txt", {"reclamo": reclamo, "EMPRESA": settings.EMPRESA})
        _enviar(f"Constancia de hoja de reclamación {reclamo.codigo}", cuerpo, [reclamo.email])
        if reclamo.sala.email_notificacion:
            url = request.build_absolute_uri(f"/panel/reclamos/{reclamo.pk}/")
            _enviar(
                f"[Libro de Reclamaciones] Nuevo {reclamo.get_tipo_display().lower()} {reclamo.codigo}",
                f"Se registró un nuevo {reclamo.get_tipo_display().lower()} en {reclamo.sala}.\n"
                f"Código: {reclamo.codigo}\nFecha límite de respuesta: {reclamo.fecha_limite:%d/%m/%Y}\n{url}\n",
                [reclamo.sala.email_notificacion],
            )


class ConstanciaView(View):
    def get(self, request, token):
        try:
            codigo = signing.loads(token, salt=SIGNING_SALT, max_age=60 * 60 * 24 * 30)
        except signing.BadSignature:
            raise Http404
        reclamo = get_object_or_404(Reclamo, codigo=codigo)
        return render(request, "reclamaciones/constancia.html", {"reclamo": reclamo})


class ConsultaView(View):
    template_name = "reclamaciones/consulta.html"
    INTENTOS_MAX = 10
    VENTANA = 600

    def _ctx(self, extra=None):
        ctx = {"form": ConsultaForm(), "salas": Sala.objects.filter(activa=True)}
        if extra:
            ctx.update(extra)
        return ctx

    def get(self, request):
        return render(request, self.template_name, self._ctx())

    def post(self, request):
        form = ConsultaForm(request.POST)
        clave = f"consulta:{_ip(request)}"
        intentos = cache.get(clave, 0)
        if intentos >= self.INTENTOS_MAX:
            form.add_error(None, "Demasiados intentos. Vuelva a intentarlo en unos minutos.")
            return render(request, self.template_name, self._ctx({"form": form}), status=429)
        reclamo = None
        if form.is_valid():
            cache.set(clave, intentos + 1, self.VENTANA)
            reclamo = Reclamo.objects.filter(
                codigo__iexact=form.cleaned_data["codigo"].strip(),
                numero_documento__iexact=form.cleaned_data["numero_documento"].strip(),
            ).first()
            if reclamo is None:
                form.add_error(None, "No encontramos una hoja de reclamación con esos datos.")
        return render(request, self.template_name, self._ctx({"form": form, "reclamo": reclamo}))


# ------------------------------------------------------------------ Panel

class StaffRequiredMixin(UserPassesTestMixin):
    login_url = "reclamaciones:login"

    def test_func(self):
        u = self.request.user
        return u.is_authenticated and u.is_staff and u.is_active


class PanelView(StaffRequiredMixin, TemplateView):
    template_name = "reclamaciones/panel.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        abiertos = Reclamo.objects.filter(estado__in=[Reclamo.Estado.PENDIENTE, Reclamo.Estado.EN_PROCESO])
        ctx["total"] = Reclamo.objects.count()
        ctx["pendientes"] = Reclamo.objects.filter(estado=Reclamo.Estado.PENDIENTE).count()
        ctx["en_proceso"] = Reclamo.objects.filter(estado=Reclamo.Estado.EN_PROCESO).count()
        ctx["respondidos"] = Reclamo.objects.filter(estado__in=[Reclamo.Estado.RESPONDIDO, Reclamo.Estado.CERRADO]).count()
        ctx["vencidos"] = abiertos.filter(fecha_limite__lt=hoy).count()
        ctx["por_vencer"] = abiertos.filter(fecha_limite__gte=hoy, fecha_limite__lte=hoy + timedelta(days=3)).count()
        ctx["por_sala"] = (
            Sala.objects.annotate(
                total=Count("reclamos"),
                abiertos=Count("reclamos", filter=Q(reclamos__estado__in=[Reclamo.Estado.PENDIENTE, Reclamo.Estado.EN_PROCESO])),
            ).order_by("-total")
        )
        ctx["recientes"] = Reclamo.objects.select_related("sala")[:8]
        return ctx


def _filtrar(request):
    form = FiltroReclamosForm(request.GET or None)
    qs = Reclamo.objects.select_related("sala", "asignado_a")
    if form.is_valid():
        d = form.cleaned_data
        if d["q"]:
            q = d["q"].strip()
            qs = qs.filter(
                Q(codigo__icontains=q) | Q(nombres__icontains=q) | Q(apellidos__icontains=q)
                | Q(numero_documento__icontains=q) | Q(email__icontains=q)
            )
        if d["sala"]:
            qs = qs.filter(sala=d["sala"])
        if d["estado"]:
            qs = qs.filter(estado=d["estado"])
        if d["tipo"]:
            qs = qs.filter(tipo=d["tipo"])
        if d["desde"]:
            qs = qs.filter(fecha_registro__date__gte=d["desde"])
        if d["hasta"]:
            qs = qs.filter(fecha_registro__date__lte=d["hasta"])
        if d["vencidos"]:
            qs = qs.filter(
                estado__in=[Reclamo.Estado.PENDIENTE, Reclamo.Estado.EN_PROCESO],
                fecha_limite__lt=timezone.localdate(),
            )
    return form, qs


class ListaReclamosView(StaffRequiredMixin, View):
    def get(self, request):
        form, qs = _filtrar(request)
        page = Paginator(qs, 20).get_page(request.GET.get("page"))
        params = request.GET.copy()
        params.pop("page", None)
        return render(request, "reclamaciones/lista.html", {
            "form": form, "page": page, "querystring": params.urlencode(),
        })


class DetalleReclamoView(StaffRequiredMixin, View):
    template_name = "reclamaciones/detalle.html"

    def get(self, request, pk):
        reclamo = get_object_or_404(Reclamo.objects.select_related("sala", "asignado_a"), pk=pk)
        return render(request, self.template_name, {"reclamo": reclamo, "form": GestionForm(instance=reclamo)})

    def post(self, request, pk):
        reclamo = get_object_or_404(Reclamo.objects.select_related("sala"), pk=pk)
        estado_anterior = reclamo.estado
        respuesta_anterior = reclamo.respuesta
        form = GestionForm(request.POST, instance=reclamo)
        if not form.is_valid():
            return render(request, self.template_name, {"reclamo": reclamo, "form": form}, status=400)
        finales = (Reclamo.Estado.RESPONDIDO, Reclamo.Estado.CERRADO)
        with transaction.atomic():
            obj = form.save(commit=False)
            es_final = obj.estado in finales
            respuesta_cambio = obj.respuesta != respuesta_anterior
            if es_final and (respuesta_cambio or obj.fecha_respuesta is None):
                obj.fecha_respuesta = timezone.now()
                obj.respondido_por = request.user
            obj.save()
            nota = form.cleaned_data.get("nota_interna", "").strip()
            if estado_anterior != obj.estado or nota:
                Seguimiento.objects.create(
                    reclamo=obj, usuario=request.user, estado=obj.estado,
                    nota=nota or f"Estado cambiado de {Reclamo.Estado(estado_anterior).label} a {obj.get_estado_display()}.",
                )
        respuesta_nueva = es_final and (respuesta_cambio or estado_anterior not in finales)
        if respuesta_nueva and form.cleaned_data.get("notificar_consumidor"):
            cuerpo = render_to_string("reclamaciones/email_respuesta.txt", {"reclamo": obj, "EMPRESA": settings.EMPRESA})
            _enviar(f"Respuesta a su hoja de reclamación {obj.codigo}", cuerpo, [obj.email])
            messages.info(request, "Se envió la respuesta al correo del consumidor.")
        messages.success(request, "Cambios guardados.")
        return redirect("reclamaciones:detalle", pk=obj.pk)


def _csv_seguro(valor):
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


class ExportarCSVView(StaffRequiredMixin, View):
    def get(self, request):
        _, qs = _filtrar(request)
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="reclamos_{timezone.localdate():%Y%m%d}.csv"'
        resp.write("\ufeff")
        w = csv.writer(resp)
        w.writerow([
            "Código", "Sala", "Fecha registro", "Fecha límite", "Estado", "Tipo", "Nombres", "Apellidos",
            "Tipo doc.", "N° doc.", "Email", "Teléfono", "Bien", "Descripción bien", "Monto (S/)",
            "Detalle", "Pedido", "Respuesta", "Fecha respuesta",
        ])
        for r in qs.iterator():
            w.writerow([_csv_seguro(x) for x in [
                r.codigo, r.sala.nombre, timezone.localtime(r.fecha_registro).strftime("%d/%m/%Y %H:%M"),
                r.fecha_limite.strftime("%d/%m/%Y") if r.fecha_limite else "", r.get_estado_display(),
                r.get_tipo_display(), r.nombres, r.apellidos, r.get_tipo_documento_display(), r.numero_documento,
                r.email, r.telefono, r.get_tipo_bien_display(), r.descripcion_bien, r.monto_reclamado or "",
                r.detalle, r.pedido, r.respuesta,
                timezone.localtime(r.fecha_respuesta).strftime("%d/%m/%Y %H:%M") if r.fecha_respuesta else "",
            ]])
        return resp


# ---------------------------------------------------------------- Configuración

class SalasView(StaffRequiredMixin, View):
    def get(self, request, pk=None):
        if pk:
            sala = get_object_or_404(Sala, pk=pk)
            return render(request, "reclamaciones/config/sala_form.html", {"form": SalaForm(instance=sala), "obj": sala})
        return render(request, "reclamaciones/config/salas.html", {"items": Sala.objects.all()})

    def post(self, request, pk=None):
        sala = get_object_or_404(Sala, pk=pk) if pk else None
        form = SalaForm(request.POST, instance=sala)
        if form.is_valid():
            form.save()
            messages.success(request, "Sala guardada correctamente.")
            return redirect("reclamaciones:salas")
        return render(request, "reclamaciones/config/sala_form.html", {"form": form, "obj": sala}, status=400)


class SalaNuevaView(StaffRequiredMixin, View):
    def get(self, request):
        return render(request, "reclamaciones/config/sala_form.html", {"form": SalaForm()})

    def post(self, request):
        form = SalaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Sala guardada correctamente.")
            return redirect("reclamaciones:salas")
        return render(request, "reclamaciones/config/sala_form.html", {"form": form}, status=400)


class SalaQRView(StaffRequiredMixin, View):
    def get(self, request, pk):
        import base64, io
        import qrcode
        sala = get_object_or_404(Sala, pk=pk)
        path = sala.get_absolute_url()
        host = getattr(settings, "SITE_URL", "").rstrip("/")
        if not host:
            allowed = [h for h in settings.ALLOWED_HOSTS if h not in ("*", "")]
            scheme = "http" if settings.DEBUG else "https"
            host = f"{scheme}://{allowed[0]}" if allowed else "http://localhost:8000"
        qr_url = f"{host}{path}"
        img = qrcode.make(qr_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        return render(request, "reclamaciones/config/sala_qr.html", {"sala": sala, "qr_b64": qr_b64, "qr_url": qr_url})


class SalaEliminarView(StaffRequiredMixin, View):
    def post(self, request, pk):
        sala = get_object_or_404(Sala, pk=pk)
        if sala.reclamos.exists():
            messages.error(request, "No se puede eliminar una sala con reclamos registrados.")
        else:
            sala.delete()
            messages.success(request, "Sala eliminada.")
        return redirect("reclamaciones:salas")


class FeriadosView(StaffRequiredMixin, View):
    def get(self, request, pk=None):
        if pk:
            feriado = get_object_or_404(Feriado, pk=pk)
            return render(request, "reclamaciones/config/feriado_form.html", {"form": FeriadoForm(instance=feriado), "obj": feriado})
        return render(request, "reclamaciones/config/feriados.html", {"items": Feriado.objects.all()})

    def post(self, request, pk=None):
        feriado = get_object_or_404(Feriado, pk=pk) if pk else None
        form = FeriadoForm(request.POST, instance=feriado)
        if form.is_valid():
            form.save()
            messages.success(request, "Feriado guardado correctamente.")
            return redirect("reclamaciones:feriados")
        return render(request, "reclamaciones/config/feriado_form.html", {"form": form, "obj": feriado}, status=400)


class FeriadoNuevoView(StaffRequiredMixin, View):
    def get(self, request):
        return render(request, "reclamaciones/config/feriado_form.html", {"form": FeriadoForm()})

    def post(self, request):
        form = FeriadoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Feriado guardado correctamente.")
            return redirect("reclamaciones:feriados")
        return render(request, "reclamaciones/config/feriado_form.html", {"form": form}, status=400)


class FeriadoEliminarView(StaffRequiredMixin, View):
    def post(self, request, pk):
        get_object_or_404(Feriado, pk=pk).delete()
        messages.success(request, "Feriado eliminado.")
        return redirect("reclamaciones:feriados")


class UsuariosView(StaffRequiredMixin, View):
    def get(self, request, pk=None):
        User = get_user_model()
        if pk:
            usuario = get_object_or_404(User, pk=pk)
            return render(request, "reclamaciones/config/usuario_form.html", {"form": UsuarioForm(instance=usuario), "obj": usuario})
        return render(request, "reclamaciones/config/usuarios.html", {"items": User.objects.order_by("username")})

    def post(self, request, pk=None):
        User = get_user_model()
        usuario = get_object_or_404(User, pk=pk) if pk else None
        form = UsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuario guardado correctamente.")
            return redirect("reclamaciones:usuarios")
        return render(request, "reclamaciones/config/usuario_form.html", {"form": form, "obj": usuario}, status=400)


class UsuarioNuevoView(StaffRequiredMixin, View):
    def get(self, request):
        return render(request, "reclamaciones/config/usuario_form.html", {"form": UsuarioForm()})

    def post(self, request):
        form = UsuarioForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuario creado correctamente.")
            return redirect("reclamaciones:usuarios")
        return render(request, "reclamaciones/config/usuario_form.html", {"form": form}, status=400)


class UsuarioEliminarView(StaffRequiredMixin, View):
    def post(self, request, pk):
        User = get_user_model()
        usuario = get_object_or_404(User, pk=pk)
        if usuario == request.user:
            messages.error(request, "No puedes eliminar tu propio usuario.")
        else:
            usuario.delete()
            messages.success(request, "Usuario eliminado.")
        return redirect("reclamaciones:usuarios")


class ConfiguracionView(StaffRequiredMixin, View):
    template_name = "reclamaciones/config/configuracion.html"

    def get(self, request):
        cfg = Configuracion.get()
        return render(request, self.template_name, {"form": ConfiguracionForm(instance=cfg)})

    def post(self, request):
        cfg = Configuracion.get()
        form = ConfiguracionForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            cfg.refresh_from_db()
            cfg.apply_to_django()
            messages.success(request, "Configuración guardada correctamente.")
            return redirect("reclamaciones:configuracion")
        return render(request, self.template_name, {"form": form}, status=400)


class TestCorreoView(StaffRequiredMixin, View):
    def post(self, request):
        from django.core.mail import send_mail
        try:
            send_mail(
                "Prueba de correo — Libro de Reclamaciones",
                "Si recibes este mensaje, la configuración SMTP está funcionando correctamente.",
                settings.DEFAULT_FROM_EMAIL,
                [request.user.email or settings.DEFAULT_FROM_EMAIL],
                fail_silently=False,
            )
            messages.success(request, f"Correo de prueba enviado a {request.user.email or settings.DEFAULT_FROM_EMAIL}.")
        except Exception as e:
            messages.error(request, f"Error al enviar: {e}")
        return redirect("reclamaciones:configuracion")
