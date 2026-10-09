# Libro de Reclamaciones

Aplicativo Django para gestionar el Libro de Reclamaciones de una empresa con varias salas de juego físicas. Incluye el **front público** (hoja de reclamación por sala) y el **panel de gestión** para el personal.

---

## Puesta en marcha

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser        # crea el primer usuario administrador (is_staff)
python manage.py cargar_demo            # opcional: crea 3 salas de ejemplo
python manage.py runserver
```

---

## URLs

| URL | Descripción |
|---|---|
| `/` | Redirige a `/consulta/` |
| `/libro/<codigo_sala>/` | Hoja de reclamación pública de una sala (ej. `/libro/MIR/`) — ideal para el QR de cada local |
| `/consulta/` | El consumidor consulta el estado de su reclamo con código + número de documento |
| `/panel/` | Dashboard (requiere `is_staff`) |
| `/panel/reclamos/` | Listado con filtros, detalle, respuesta y exportación CSV |
| `/panel/salas/` | Gestión de salas de juego |
| `/panel/feriados/` | Gestión de feriados para el cómputo de plazos |
| `/panel/usuarios/` | Gestión de usuarios del panel |
| `/panel/configuracion/` | Configuración general: empresa, SMTP, plazo de respuesta |

---

## Configuración

La configuración principal se gestiona desde **`/panel/configuracion/`** (modelo `Configuracion`, singleton). También se puede configurar mediante variables de entorno en `settings.py`:

### Django
| Variable | Descripción |
|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta de Django |
| `DJANGO_DEBUG` | `True` / `False` |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos separados por coma |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Orígenes de confianza para CSRF |

### Empresa
| Variable | Descripción |
|---|---|
| `EMPRESA_RAZON_SOCIAL` | Razón social |
| `EMPRESA_NOMBRE` | Nombre comercial |
| `EMPRESA_RUC` | RUC (11 dígitos) |
| `EMPRESA_DOMICILIO` | Domicilio fiscal |

### Correo
| Variable | Descripción |
|---|---|
| `EMAIL_BACKEND` | Por defecto imprime en consola (`django.core.mail.backends.console.EmailBackend`) |
| `EMAIL_HOST` | Servidor SMTP |
| `EMAIL_PORT` | Puerto SMTP (por defecto 587) |
| `EMAIL_HOST_USER` | Usuario SMTP |
| `EMAIL_HOST_PASSWORD` | Contraseña SMTP |
| `EMAIL_USE_TLS` | `True` / `False` |
| `DEFAULT_FROM_EMAIL` | Correo remitente |

### Plazos
| Variable | Descripción |
|---|---|
| `PLAZO_RESPUESTA_DIAS_HABILES` | Días hábiles para responder (por defecto 15). **Validar con el área legal.** |

---

## Funcionamiento

- **Correlativo por sala y año**: `MIR-2026-000001` (tabla `Correlativo`, incremento atómico con `select_for_update`).
- **Fecha límite**: calculada en días hábiles desde el registro, omitiendo sábados, domingos y los feriados cargados en `/panel/feriados/`.
- **Estados del reclamo**: `Pendiente` → `En proceso` → `Respondido` → `Cerrado`. Cada cambio queda registrado en el historial (`Seguimiento`).
- **Correos automáticos**:
  - Constancia al consumidor al registrar el reclamo.
  - Aviso a la sala (campo *correo de notificación*) con el código y la fecha límite.
  - Respuesta al consumidor al marcar el reclamo como respondido/cerrado (opcional).
- **Anti-spam**: campo trampa (`sitio_web`) oculto; si llega con valor, el formulario se rechaza.
- **Seguridad**:
  - Panel solo accesible para usuarios con `is_staff = True`.
  - Constancia con enlace firmado (válido 30 días).
  - Límite de 10 intentos por IP en la consulta pública (ventana de 10 minutos).
  - CSV protegido contra inyección de fórmulas.
  - Los reclamos no se pueden borrar desde el admin de Django.
- **Datos personales**: la hoja incluye la aceptación de tratamiento de datos (Ley N° 29733). Completar con la política de privacidad y el aviso/inscripción del banco de datos según corresponda.

---

## Modelos principales

| Modelo | Descripción |
|---|---|
| `Configuracion` | Singleton con datos de empresa y SMTP |
| `Sala` | Sala de juego física (código, nombre, dirección, correo de notificación) |
| `Reclamo` | Hoja de reclamación completa |
| `Seguimiento` | Historial de cambios de estado de un reclamo |
| `Correlativo` | Contador por sala y año para el código único |
| `Feriado` | Días no laborables para el cómputo de plazos |

---

## Migración a PostgreSQL

```bash
pip install "psycopg[binary]"
python manage.py dumpdata --natural-foreign --natural-primary \
    -e contenttypes -e auth.Permission --indent 2 > datos.json

# Definir variables de entorno de la BD
set DB_ENGINE=postgres
set DB_NAME=libro_reclamaciones
set DB_USER=...
set DB_PASSWORD=...
set DB_HOST=...
set DB_PORT=5432

python manage.py migrate
python manage.py loaddata datos.json
```

Si aún no hay datos reales, basta con definir las variables y ejecutar `migrate`.

---

## Pruebas

```bash
python manage.py test
```

---

## Producción (checklist)

- [ ] `DJANGO_DEBUG=False` y `DJANGO_SECRET_KEY` segura.
- [ ] Servir con **gunicorn** + **Nginx** (o **WhiteNoise** para estáticos).
- [ ] `python manage.py collectstatic`.
- [ ] HTTPS obligatorio; configurar `DJANGO_CSRF_TRUSTED_ORIGINS`.
- [ ] Configurar SMTP real en `/panel/configuracion/` y verificar con "Enviar correo de prueba".
- [ ] Generar un QR por sala desde `/panel/salas/<id>/qr/` apuntando a `/libro/<codigo>/`.
- [ ] Programar respaldos periódicos de la base de datos.
- [ ] Revisar con legal el contenido de la hoja, los textos del plazo y el aviso INDECOPI.

---

## Dependencias

```
Django >= 5.1, < 6
qrcode[pil] >= 7.4
# Opcional:
# psycopg[binary] >= 3.2   (PostgreSQL)
# gunicorn                  (producción)
# whitenoise                (estáticos en producción)
```
