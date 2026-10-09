from datetime import date, timedelta

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone


class Empresa(models.Model):
    """Empresa operadora. Cada empresa tiene sus propias salas y configuración SMTP."""

    razon_social = models.CharField(max_length=200)
    nombre_comercial = models.CharField(max_length=120)
    ruc = models.CharField(
        max_length=11, unique=True,
        validators=[RegexValidator(r"^\d{11}$", "El RUC debe tener 11 dígitos.")],
    )
    domicilio_fiscal = models.CharField(max_length=200)
    plazo_dias_habiles = models.PositiveIntegerField(
        "plazo de respuesta (días hábiles)", default=15,
        help_text="Verificar vigencia con el área legal.",
    )

    # Correo saliente
    email_host = models.CharField("servidor SMTP", max_length=200, blank=True, default="")
    email_port = models.PositiveIntegerField("puerto SMTP", default=587)
    email_host_user = models.CharField("usuario SMTP", max_length=200, blank=True, default="")
    email_host_password = models.CharField("contraseña SMTP", max_length=200, blank=True, default="")
    email_use_tls = models.BooleanField("usar TLS", default=True)
    email_from = models.EmailField(
        "correo remitente", default="reclamos@example.com",
        help_text="Dirección desde la que se envían las constancias y respuestas.",
    )

    class Meta:
        ordering = ["razon_social"]
        verbose_name = "empresa"
        verbose_name_plural = "empresas"

    def __str__(self):
        return f"{self.nombre_comercial} ({self.ruc})"

    def get_email_connection(self):
        """Devuelve kwargs para get_connection() con la config SMTP de esta empresa."""
        if not self.email_host:
            return {}
        return {
            "backend": "django.core.mail.backends.smtp.EmailBackend",
            "host": self.email_host,
            "port": self.email_port,
            "username": self.email_host_user,
            "password": self.email_host_password,
            "use_tls": self.email_use_tls,
        }


class Feriado(models.Model):
    """Días no laborables adicionales a sábados y domingos (para el cómputo de plazos)."""

    fecha = models.DateField(unique=True)
    descripcion = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["fecha"]
        verbose_name = "feriado"
        verbose_name_plural = "feriados"

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y} {self.descripcion}".strip()


def sumar_dias_habiles(inicio: date, dias: int) -> date:
    """Suma `dias` días hábiles a `inicio`, omitiendo sábados, domingos y feriados registrados."""
    feriados = set(Feriado.objects.filter(fecha__gte=inicio).values_list("fecha", flat=True))
    actual = inicio
    restantes = dias
    while restantes > 0:
        actual += timedelta(days=1)
        if actual.weekday() < 5 and actual not in feriados:
            restantes -= 1
    return actual


class Sala(models.Model):
    """Sala de juego física (local). Cada sala pertenece a una empresa."""

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="salas")
    codigo = models.SlugField(
        "código", max_length=10,
        help_text="Código corto usado en el correlativo y en la URL. Ej.: MIR, SMP, CHO",
    )
    nombre = models.CharField(max_length=120)
    direccion = models.CharField("dirección", max_length=200)
    distrito = models.CharField(max_length=80, blank=True)
    email_notificacion = models.EmailField(
        "correo de notificación", blank=True,
        help_text="Recibe un aviso cada vez que se registra un reclamo en esta sala.",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        unique_together = [("empresa", "codigo")]
        verbose_name = "sala de juego"
        verbose_name_plural = "salas de juego"

    def __str__(self):
        return f"{self.nombre} ({self.empresa.nombre_comercial})"

    def get_absolute_url(self):
        return reverse("reclamaciones:hoja", args=[self.empresa.ruc, self.codigo])


class OperadorSala(models.Model):
    """Relación entre un usuario operador y las salas que puede gestionar."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="salas_asignadas"
    )
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name="operadores")

    class Meta:
        unique_together = [("usuario", "sala")]
        verbose_name = "asignación operador-sala"
        verbose_name_plural = "asignaciones operador-sala"

    def __str__(self):
        return f"{self.usuario} → {self.sala}"


class Correlativo(models.Model):
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name="correlativos")
    anio = models.PositiveIntegerField()
    ultimo = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("sala", "anio")]

    @classmethod
    def siguiente(cls, sala, anio):
        with transaction.atomic():
            obj, _ = cls.objects.select_for_update().get_or_create(sala=sala, anio=anio)
            obj.ultimo += 1
            obj.save(update_fields=["ultimo"])
            return obj.ultimo


class Reclamo(models.Model):
    class TipoDocumento(models.TextChoices):
        DNI = "DNI", "DNI"
        CE = "CE", "Carné de extranjería"
        PASAPORTE = "PAS", "Pasaporte"
        RUC = "RUC", "RUC"

    class TipoBien(models.TextChoices):
        PRODUCTO = "PRODUCTO", "Producto"
        SERVICIO = "SERVICIO", "Servicio"

    class Tipo(models.TextChoices):
        RECLAMO = "RECLAMO", "Reclamo"
        QUEJA = "QUEJA", "Queja"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        RESPONDIDO = "RESPONDIDO", "Respondido"
        CERRADO = "CERRADO", "Cerrado"

    codigo = models.CharField(max_length=30, unique=True, editable=False)
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="reclamos")
    sala = models.ForeignKey(Sala, on_delete=models.PROTECT, related_name="reclamos")
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)
    fecha_limite = models.DateField("fecha límite de respuesta", null=True, blank=True)

    # 1. Identificación del consumidor reclamante
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    tipo_documento = models.CharField(max_length=3, choices=TipoDocumento.choices, default=TipoDocumento.DNI)
    numero_documento = models.CharField(
        "número de documento", max_length=20,
        validators=[RegexValidator(r"^[A-Za-z0-9\-]{6,20}$", "Ingrese un número de documento válido.")],
    )
    domicilio = models.CharField(max_length=200)
    telefono = models.CharField("teléfono", max_length=20, blank=True)
    email = models.EmailField("correo electrónico")

    # 2. Identificación del bien contratado
    tipo_bien = models.CharField(max_length=10, choices=TipoBien.choices, default=TipoBien.SERVICIO)
    descripcion_bien = models.CharField("descripción del producto o servicio", max_length=250)
    monto_reclamado = models.DecimalField(
        "monto reclamado (S/)", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    fecha_incidente = models.DateField("fecha del incidente", null=True, blank=True)

    # 3. Detalle de la reclamación y pedido del consumidor
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.RECLAMO)
    detalle = models.TextField("detalle")
    pedido = models.TextField("pedido del consumidor")

    # Metadatos del registro
    acepta_terminos = models.BooleanField(default=False)
    ip_origen = models.GenericIPAddressField(null=True, blank=True, editable=False)

    # 4. Gestión interna (panel)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    asignado_a = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reclamos_asignados", verbose_name="asignado a",
    )
    acciones_adoptadas = models.TextField("acciones adoptadas por el proveedor", blank=True)
    respuesta = models.TextField("respuesta al consumidor", blank=True)
    fecha_respuesta = models.DateTimeField(null=True, blank=True)
    respondido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reclamos_respondidos",
    )

    class Meta:
        ordering = ["-fecha_registro"]
        verbose_name = "hoja de reclamación"
        verbose_name_plural = "hojas de reclamación"
        permissions = [("exportar_reclamo", "Puede exportar reclamos a CSV")]

    def __str__(self):
        return f"{self.codigo} - {self.nombre_completo}"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def esta_vencido(self):
        return (
            self.estado in (self.Estado.PENDIENTE, self.Estado.EN_PROCESO)
            and self.fecha_limite is not None
            and self.fecha_limite < timezone.localdate()
        )

    @property
    def dias_restantes(self):
        if self.fecha_limite is None:
            return None
        return (self.fecha_limite - timezone.localdate()).days

    def save(self, *args, **kwargs):
        if not self.codigo:
            ahora = self.fecha_registro or timezone.now()
            anio = timezone.localtime(ahora).year
            numero = Correlativo.siguiente(self.sala, anio)
            self.codigo = f"{self.sala.codigo.upper()}-{anio}-{numero:06d}"
        if self.fecha_limite is None:
            inicio = timezone.localtime(self.fecha_registro).date()
            self.fecha_limite = sumar_dias_habiles(inicio, self.empresa.plazo_dias_habiles)
        super().save(*args, **kwargs)


class Seguimiento(models.Model):
    """Historial de acciones sobre un reclamo (auditoría)."""

    reclamo = models.ForeignKey(Reclamo, on_delete=models.CASCADE, related_name="seguimientos")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    fecha = models.DateTimeField(default=timezone.now)
    estado = models.CharField(max_length=12, choices=Reclamo.Estado.choices)
    nota = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "seguimiento"
        verbose_name_plural = "seguimientos"

    def __str__(self):
        return f"{self.reclamo.codigo} · {self.get_estado_display()}"
