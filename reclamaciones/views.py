import csv
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core import signing
from django.core.cache import cache
from django.core.mail import get_connection, send_mail
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
    EmpresaForm, ConsultaForm, FeriadoForm, FiltroReclamosForm,
    GestionForm, HojaReclamacionForm, SalaForm, UsuarioForm,
)
from .models import Empresa, Feriado, OperadorSala, Reclamo, Sala, Seguimiento

logger = logging.getLogger(__name__)

SIGNING_SALT = "reclamaciones.constancia"


def _ip(request):
    return request.META.get("REMOTE_ADDR")


def _enviar(asunto, cuerpo, destinatarios, empresa=None):
    destinatarios = [d for d in destinatarios if d]
    if not destinatarios:
        return
    try:
        from_email = settings.DEFAULT_FROM_EMAIL
        connection = None
        if empresa:
            kwargs = empresa.get_email_connection()
            if kwargs:
                from_email = empresa.email_from
                connection = get_connection(**kwargs)
        send_mail(asunto, cuerpo, from_email, destinatarios,
                  connection=connection, fail_silently=False)
    except Exception:
        logger.exception("No se pudo enviar el correo '%s'", asunto)


def _salas_del_usuario(user):
    """Devuelve el queryset de salas visibles para el usuario."""
    if user.is_superuser:
        return Sala.objects.select_related("empresa").all()
    return Sala.objects.select_related("empresa").filter(operadores__usuario=user)


def _reclamos_del_usuario(user):
    """Devuelve el queryset base de reclamos visibles para el usuario."""
    qs = Reclamo.objects.select_related("empresa", "sala", "asignado_a")
    if user.is_superuser:
        return qs
    salas = _salas_del_usuario(user)
    return qs.filter(sala__in=salas)


# ---------------------------------------------------------------- Front público

class HojaReclamacionView(View):
    template_name = "reclamaciones/hoja.html"

    def _get_sala(self, ruc, sala_codigo):
        empresa = get_object_or_404(Empresa, ruc=ruc)
        return get_object_or_404(Sala, empresa=empresa, codigo__iexact=sala_codigo, activa=True)

    def get(self, request, ruc, sala_codigo):
        sala = self._get_sala(ruc, sala_codigo)
        return render(request, self.template_name, {"sala": sala, "form": HojaReclamacionForm()})

    def post(self, request, ruc, sala_codigo):
        sala = self._get_sala(ruc, sala_codigo)
        form = HojaReclamacionForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                reclamo = form.save(commit=False)
                reclamo.sala = sala
                reclamo.empresa = sala.empresa
                reclamo.ip_origen = _ip(request)
                reclamo.save()
                Seguimiento.objects.create(
                    reclamo=reclamo, estado=reclamo.estado,
                    nota="Hoja de reclamación registrada por el consumidor."
                )
            self._notificar(request, reclamo)
            token = signing.dumps(reclamo.codigo, salt=SIGNING_SALT)
            return redirect("reclamaciones:constancia", token=token)
        return render(request, self.template_name, {"sala": sala, "form": form}, status=400)

    def _notificar(self, request, reclamo):
        empresa = reclamo.empresa
        ctx = {"reclamo": reclamo, "EMPRESA": {
            "razon_social": empresa.razon_social,
            "nombre_comercial": empresa.nombre_comercial,
            "ruc": empresa.ruc,
            "domicilio_fiscal": empresa.domicilio_fiscal,
        }}
        cuerpo = render_to_string("reclamaciones/email_constancia.txt", ctx)
        _enviar(f"Constancia de hoja de reclamación {reclamo.codigo}", cuerpo,
                [reclamo.email], empresa=empresa)
        if reclamo.sala.email_notificacion:
            url = request.build_absolute_uri(f"/panel/reclamos/{reclamo.pk}/")
            _enviar(
                f"[Libro de Reclamaciones] Nuevo {reclamo.get_tipo_display().lower()} {reclamo.codigo}",
                f"Se registró un nuevo {reclamo.get_tipo_display().lower()} en {reclamo.sala}.\n"
                f"Código: {reclamo.codigo}\nFecha límite de respuesta: {reclamo.fecha_limite:%d/%m/%Y}\n{url}\n",
                [reclamo.sala.email_notificacion], empresa=empresa,
            )


class ConstanciaView(View):
    def get(self, request, token):
        try:
            codigo = signing.loads(token, salt=SIGNING_SALT, max_age=60 * 60 * 24 * 30)
        except signing.BadSignature:
            raise Http404
        reclamo = get_object_or_404(Reclamo.objects.select_related("empresa"), codigo=codigo)
        return render(request, "reclamaciones/constancia.html", {"reclamo": reclamo})


class ConsultaView(View):
    template_name = "reclamaciones/consulta.html"
    INTENTOS_MAX = 10
    VENTANA = 600

    def _ctx(self, extra=None):
        ctx = {"form": ConsultaForm(), "empresas": Empresa.objects.prefetch_related("salas")}
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
            reclamo = Reclamo.objects.select_related("empresa", "sala").filter(
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


class AdminRequiredMixin(UserPassesTestMixin):
    """Solo superusuarios pueden acceder (empresas, salas, feriados, usuarios)."""
    login_url = "reclamaciones:login"

    def test_func(self):
        u = self.request.user
        return u.is_authenticated and u.is_superuser and u.is_active

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para acceder a esta sección.")
        return redirect("reclamaciones:panel")


class PanelView(StaffRequiredMixin, TemplateView):
    template_name = "reclamaciones/panel.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        qs_base = _reclamos_del_usuario(self.request.user)
        abiertos = qs_base.filter(estado__in=[Reclamo.Estado.PENDIENTE, Reclamo.Estado.EN_PROCESO])
        ctx["total"] = qs_base.count()
        ctx["pendientes"] = qs_base.filter(estado=Reclamo.Estado.PENDIENTE).count()
        ctx["en_proceso"] = qs_base.filter(estado=Reclamo.Estado.EN_PROCESO).count()
        ctx["respondidos"] = qs_base.filter(estado__in=[Reclamo.Estado.RESPONDIDO, Reclamo.Estado.CERRADO]).count()
        ctx["vencidos"] = abiertos.filter(fecha_limite__lt=hoy).count()
        ctx["por_vencer"] = abiertos.filter(fecha_limite__gte=hoy, fecha_limite__lte=hoy + timedelta(days=3)).count()
        salas_visibles = _salas_del_usuario(self.request.user)
        ctx["por_sala"] = salas_visibles.annotate(
            total=Count("reclamos"),
            abiertos=Count("reclamos", filter=Q(reclamos__estado__in=[Reclamo.Estado.PENDIENTE, Reclamo.Estado.EN_PROCESO])),
        ).order_by("-total")
        ctx["recientes"] = qs_base.select_related("sala", "empresa")[:8]
        return ctx


def _filtrar(request):
    user = request.user
    form = FiltroReclamosForm(request.GET or None)
    qs = _reclamos_del_usuario(user)

    # Limitar opciones del filtro de sala a las visibles por el usuario
    if not user.is_superuser:
        form.fields["sala"].queryset = _salas_del_usuario(user)
        form.fields["empresa"].queryset = Empresa.objects.filter(salas__operadores__usuario=user).distinct()

    if form.is_valid():
        d = form.cleaned_data
        if d["q"]:
            q = d["q"].strip()
            qs = qs.filter(
                Q(codigo__icontains=q) | Q(nombres__icontains=q) | Q(apellidos__icontains=q)
                | Q(numero_documento__icontains=q) | Q(email__icontains=q)
            )
        if d.get("empresa"):
            qs = qs.filter(empresa=d["empresa"])
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

    def _get_reclamo(self, request, pk):
        qs = _reclamos_del_usuario(request.user)
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        reclamo = self._get_reclamo(request, pk)
        return render(request, self.template_name, {"reclamo": reclamo, "form": GestionForm(instance=reclamo)})

    def post(self, request, pk):
        reclamo = self._get_reclamo(request, pk)
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
            empresa = obj.empresa
            ctx = {"reclamo": obj, "EMPRESA": {
                "razon_social": empresa.razon_social,
                "nombre_comercial": empresa.nombre_comercial,
                "ruc": empresa.ruc,
                "domicilio_fiscal": empresa.domicilio_fiscal,
            }}
            cuerpo = render_to_string("reclamaciones/email_respuesta.txt", ctx)
            _enviar(f"Respuesta a su hoja de reclamación {obj.codigo}", cuerpo,
                    [obj.email], empresa=empresa)
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
            "Código", "Empresa", "Sala", "Fecha registro", "Fecha límite", "Estado", "Tipo",
            "Nombres", "Apellidos", "Tipo doc.", "N° doc.", "Email", "Teléfono",
            "Bien", "Descripción bien", "Monto (S/)", "Detalle", "Pedido", "Respuesta", "Fecha respuesta",
        ])
        for r in qs.iterator():
            w.writerow([_csv_seguro(x) for x in [
                r.codigo, r.empresa.nombre_comercial, r.sala.nombre,
                timezone.localtime(r.fecha_registro).strftime("%d/%m/%Y %H:%M"),
                r.fecha_limite.strftime("%d/%m/%Y") if r.fecha_limite else "",
                r.get_estado_display(), r.get_tipo_display(),
                r.nombres, r.apellidos, r.get_tipo_documento_display(), r.numero_documento,
                r.email, r.telefono, r.get_tipo_bien_display(), r.descripcion_bien,
                r.monto_reclamado or "", r.detalle, r.pedido, r.respuesta,
                timezone.localtime(r.fecha_respuesta).strftime("%d/%m/%Y %H:%M") if r.fecha_respuesta else "",
            ]])
        return resp


# ---------------------------------------------------------------- Empresas

class EmpresasView(AdminRequiredMixin, View):
    def get(self, request, pk=None):
        if pk:
            empresa = get_object_or_404(Empresa, pk=pk)
            return render(request, "reclamaciones/config/empresa_form.html",
                          {"form": EmpresaForm(instance=empresa), "obj": empresa})
        return render(request, "reclamaciones/config/empresas.html",
                      {"items": Empresa.objects.annotate(total_salas=Count("salas"))})

    def post(self, request, pk=None):
        empresa = get_object_or_404(Empresa, pk=pk) if pk else None
        form = EmpresaForm(request.POST, instance=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, "Empresa guardada correctamente.")
            return redirect("reclamaciones:empresas")
        return render(request, "reclamaciones/config/empresa_form.html",
                      {"form": form, "obj": empresa}, status=400)


class EmpresaNuevaView(AdminRequiredMixin, View):
    def get(self, request):
        return render(request, "reclamaciones/config/empresa_form.html", {"form": EmpresaForm()})

    def post(self, request):
        form = EmpresaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Empresa creada correctamente.")
            return redirect("reclamaciones:empresas")
        return render(request, "reclamaciones/config/empresa_form.html", {"form": form}, status=400)


class EmpresaEliminarView(AdminRequiredMixin, View):
    def post(self, request, pk):
        empresa = get_object_or_404(Empresa, pk=pk)
        if empresa.salas.exists():
            messages.error(request, "No se puede eliminar una empresa con salas registradas.")
        else:
            empresa.delete()
            messages.success(request, "Empresa eliminada.")
        return redirect("reclamaciones:empresas")


class TestCorreoEmpresaView(AdminRequiredMixin, View):
    def post(self, request, pk):
        empresa = get_object_or_404(Empresa, pk=pk)
        try:
            _enviar(
                "Prueba de correo — Libro de Reclamaciones",
                "Si recibes este mensaje, la configuración SMTP está funcionando correctamente.",
                [request.user.email or empresa.email_from],
                empresa=empresa,
            )
            messages.success(request, f"Correo de prueba enviado a {request.user.email or empresa.email_from}.")
        except Exception as e:
            messages.error(request, f"Error al enviar: {e}")
        return redirect("reclamaciones:empresa_editar", pk=pk)


# ---------------------------------------------------------------- Salas

class SalasView(AdminRequiredMixin, View):
    def get(self, request, pk=None):
        if pk:
            sala = get_object_or_404(Sala, pk=pk)
            return render(request, "reclamaciones/config/sala_form.html",
                          {"form": SalaForm(instance=sala), "obj": sala})
        return render(request, "reclamaciones/config/salas.html",
                      {"items": Sala.objects.select_related("empresa").all()})

    def post(self, request, pk=None):
        sala = get_object_or_404(Sala, pk=pk) if pk else None
        form = SalaForm(request.POST, instance=sala)
        if form.is_valid():
            form.save()
            messages.success(request, "Sala guardada correctamente.")
            return redirect("reclamaciones:salas")
        return render(request, "reclamaciones/config/sala_form.html",
                      {"form": form, "obj": sala}, status=400)


class SalaNuevaView(AdminRequiredMixin, View):
    def get(self, request):
        return render(request, "reclamaciones/config/sala_form.html", {"form": SalaForm()})

    def post(self, request):
        form = SalaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Sala guardada correctamente.")
            return redirect("reclamaciones:salas")
        return render(request, "reclamaciones/config/sala_form.html", {"form": form}, status=400)


class SalaQRView(AdminRequiredMixin, View):
    def get(self, request, pk):
        import base64, io
        import qrcode
        sala = get_object_or_404(Sala.objects.select_related("empresa"), pk=pk)
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
        return render(request, "reclamaciones/config/sala_qr.html",
                      {"sala": sala, "qr_b64": qr_b64, "qr_url": qr_url})


class SalaEliminarView(AdminRequiredMixin, View):
    def post(self, request, pk):
        sala = get_object_or_404(Sala, pk=pk)
        if sala.reclamos.exists():
            messages.error(request, "No se puede eliminar una sala con reclamos registrados.")
        else:
            sala.delete()
            messages.success(request, "Sala eliminada.")
        return redirect("reclamaciones:salas")


# ---------------------------------------------------------------- Feriados

class FeriadosView(AdminRequiredMixin, View):
    def get(self, request, pk=None):
        if pk:
            feriado = get_object_or_404(Feriado, pk=pk)
            return render(request, "reclamaciones/config/feriado_form.html",
                          {"form": FeriadoForm(instance=feriado), "obj": feriado})
        return render(request, "reclamaciones/config/feriados.html", {"items": Feriado.objects.all()})

    def post(self, request, pk=None):
        feriado = get_object_or_404(Feriado, pk=pk) if pk else None
        form = FeriadoForm(request.POST, instance=feriado)
        if form.is_valid():
            form.save()
            messages.success(request, "Feriado guardado correctamente.")
            return redirect("reclamaciones:feriados")
        return render(request, "reclamaciones/config/feriado_form.html",
                      {"form": form, "obj": feriado}, status=400)


class FeriadoNuevoView(AdminRequiredMixin, View):
    def get(self, request):
        return render(request, "reclamaciones/config/feriado_form.html", {"form": FeriadoForm()})

    def post(self, request):
        form = FeriadoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Feriado guardado correctamente.")
            return redirect("reclamaciones:feriados")
        return render(request, "reclamaciones/config/feriado_form.html", {"form": form}, status=400)


class FeriadoEliminarView(AdminRequiredMixin, View):
    def post(self, request, pk):
        get_object_or_404(Feriado, pk=pk).delete()
        messages.success(request, "Feriado eliminado.")
        return redirect("reclamaciones:feriados")


# ---------------------------------------------------------------- Usuarios

class UsuariosView(AdminRequiredMixin, View):
    def get(self, request, pk=None):
        User = get_user_model()
        if pk:
            usuario = get_object_or_404(User, pk=pk)
            return render(request, "reclamaciones/config/usuario_form.html",
                          {"form": UsuarioForm(instance=usuario), "obj": usuario})
        return render(request, "reclamaciones/config/usuarios.html",
                      {"items": User.objects.order_by("username")})

    def post(self, request, pk=None):
        User = get_user_model()
        usuario = get_object_or_404(User, pk=pk) if pk else None
        form = UsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuario guardado correctamente.")
            return redirect("reclamaciones:usuarios")
        return render(request, "reclamaciones/config/usuario_form.html",
                      {"form": form, "obj": usuario}, status=400)


class UsuarioNuevoView(AdminRequiredMixin, View):
    def get(self, request):
        return render(request, "reclamaciones/config/usuario_form.html", {"form": UsuarioForm()})

    def post(self, request):
        form = UsuarioForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuario creado correctamente.")
            return redirect("reclamaciones:usuarios")
        return render(request, "reclamaciones/config/usuario_form.html", {"form": form}, status=400)


class UsuarioEliminarView(AdminRequiredMixin, View):
    def post(self, request, pk):
        User = get_user_model()
        usuario = get_object_or_404(User, pk=pk)
        if usuario == request.user:
            messages.error(request, "No puedes eliminar tu propio usuario.")
        else:
            usuario.delete()
            messages.success(request, "Usuario eliminado.")
        return redirect("reclamaciones:usuarios")
