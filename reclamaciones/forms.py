import re

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Feriado, Reclamo, Sala


class ConfiguracionForm(forms.ModelForm):
    email_host_password = forms.CharField(
        label="Contraseña SMTP", widget=forms.PasswordInput(render_value=True), required=False
    )

    class Meta:
        from .models import Configuracion
        model = Configuracion
        fields = [
            "razon_social", "nombre_comercial", "ruc", "domicilio_fiscal", "plazo_dias_habiles",
            "email_host", "email_port", "email_host_user", "email_host_password", "email_use_tls", "email_from",
        ]


class HojaReclamacionForm(forms.ModelForm):
    # Campo trampa anti-spam (debe llegar vacío)
    sitio_web = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = Reclamo
        fields = [
            "nombres", "apellidos", "tipo_documento", "numero_documento", "domicilio",
            "telefono", "email",
            "tipo_bien", "descripcion_bien", "monto_reclamado", "fecha_incidente",
            "tipo", "detalle", "pedido", "acepta_terminos",
        ]
        widgets = {
            "detalle": forms.Textarea(attrs={"rows": 5}),
            "pedido": forms.Textarea(attrs={"rows": 3}),
            "fecha_incidente": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "tipo": forms.RadioSelect,
            "tipo_bien": forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["acepta_terminos"].required = True
        self.fields["acepta_terminos"].label = (
            "Declaro que la información consignada es veraz y autorizo el tratamiento de mis datos "
            "personales para la atención de este reclamo (Ley N° 29733)."
        )
        self.fields["tipo"].choices = Reclamo.Tipo.choices

    def clean_sitio_web(self):
        if self.cleaned_data.get("sitio_web"):
            raise forms.ValidationError("Solicitud inválida.")
        return ""

    def clean(self):
        data = super().clean()
        tipo_doc = data.get("tipo_documento")
        numero = (data.get("numero_documento") or "").strip()
        if tipo_doc == Reclamo.TipoDocumento.DNI and not re.fullmatch(r"\d{8}", numero):
            self.add_error("numero_documento", "El DNI debe tener 8 dígitos.")
        if tipo_doc == Reclamo.TipoDocumento.RUC and not re.fullmatch(r"\d{11}", numero):
            self.add_error("numero_documento", "El RUC debe tener 11 dígitos.")
        fecha = data.get("fecha_incidente")
        if fecha and fecha > timezone.localdate():
            self.add_error("fecha_incidente", "La fecha del incidente no puede ser futura.")
        monto = data.get("monto_reclamado")
        if monto is not None and monto < 0:
            self.add_error("monto_reclamado", "El monto no puede ser negativo.")
        data["numero_documento"] = numero
        return data


class ConsultaForm(forms.Form):
    codigo = forms.CharField(label="Código de la hoja de reclamación", max_length=30)
    numero_documento = forms.CharField(label="Número de documento del reclamante", max_length=20)


class GestionForm(forms.ModelForm):
    """Edición interna del reclamo desde el panel."""

    class Meta:
        model = Reclamo
        fields = ["estado", "asignado_a", "acciones_adoptadas", "respuesta"]
        widgets = {
            "acciones_adoptadas": forms.Textarea(attrs={"rows": 3}),
            "respuesta": forms.Textarea(attrs={"rows": 6}),
        }

    nota_interna = forms.CharField(
        label="Nota interna (queda en el historial)", required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    notificar_consumidor = forms.BooleanField(
        label="Enviar la respuesta por correo al consumidor", required=False, initial=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["asignado_a"].queryset = User.objects.filter(is_active=True, is_staff=True)
        self.fields["asignado_a"].required = False

    def clean(self):
        data = super().clean()
        estado = data.get("estado")
        if estado in (Reclamo.Estado.RESPONDIDO, Reclamo.Estado.CERRADO) and not (data.get("respuesta") or "").strip():
            self.add_error("respuesta", "Debe registrar la respuesta al consumidor para marcar el reclamo como respondido o cerrado.")
        return data


class SalaForm(forms.ModelForm):
    class Meta:
        model = Sala
        fields = ["codigo", "nombre", "direccion", "distrito", "email_notificacion", "activa"]


class FeriadoForm(forms.ModelForm):
    class Meta:
        from .models import Feriado
        model = Feriado
        fields = ["fecha", "descripcion"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class UsuarioForm(forms.ModelForm):
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput, required=False,
                                help_text="Dejar en blanco para no cambiarla.")
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput, required=False)

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_staff"]

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1", ""), data.get("password2", "")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            elif len(p1) < 8:
                self.add_error("password1", "Mínimo 8 caracteres.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        p = self.cleaned_data.get("password1")
        if p:
            user.set_password(p)
        elif not user.pk:  # nuevo usuario sin contraseña
            user.set_unusable_password()
        if commit:
            user.save()
        return user


class FiltroReclamosForm(forms.Form):
    q = forms.CharField(required=False, label="Buscar", widget=forms.TextInput(attrs={"placeholder": "Código, nombre, documento o email"}))
    sala = forms.ModelChoiceField(queryset=Sala.objects.all(), required=False, empty_label="Todas las salas")
    estado = forms.ChoiceField(required=False, choices=[("", "Todos los estados")] + list(Reclamo.Estado.choices))
    tipo = forms.ChoiceField(required=False, choices=[("", "Reclamo y queja")] + list(Reclamo.Tipo.choices))
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    vencidos = forms.BooleanField(required=False, label="Solo vencidos")
