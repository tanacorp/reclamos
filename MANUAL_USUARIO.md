# Manual de Usuario — Libro de Reclamaciones

---

## Para el consumidor

### 1. Registrar una hoja de reclamación

1. Escanea el **código QR** del local o ingresa directamente a la dirección que te indicó el establecimiento (ej. `https://ejemplo.com/libro/MIR/`).
2. Verás el formulario dividido en cuatro pasos:

   **Paso 1 — Tus datos personales**
   - Ingresa tu nombre, apellidos, tipo y número de documento.
   - Escribe tu domicilio, teléfono (opcional) y correo electrónico.
   - El correo es importante: ahí recibirás la constancia y la respuesta del establecimiento.

   **Paso 2 — El producto o servicio**
   - Selecciona si tu reclamo es sobre un **Producto** o un **Servicio**.
   - Describe brevemente el producto o servicio involucrado.
   - Puedes indicar el monto reclamado y la fecha en que ocurrió el incidente (opcionales).

   **Paso 3 — Tu reclamo o queja**
   - Elige entre **Reclamo** (disconformidad con el producto/servicio) o **Queja** (malestar por la atención).
   - Explica con detalle lo que ocurrió.
   - Indica qué solución esperas del establecimiento.

   **Paso 4 — Confirmación**
   - Marca la casilla de aceptación de términos y tratamiento de datos.
   - Haz clic en **Enviar hoja de reclamación**.

3. Si todo es correcto, verás tu **constancia** con el código único de tu reclamo (ej. `MIR-2026-000001`) y la fecha límite de respuesta. También recibirás una copia por correo electrónico.

> **Guarda tu código de reclamo.** Lo necesitarás para consultar el estado.

---

### 2. Consultar el estado de tu reclamo

1. Ingresa a `/consulta/` en el sitio del establecimiento.
2. Escribe tu **código de reclamo** y tu **número de documento**.
3. Haz clic en **Consultar**.
4. Verás el estado actual: `Pendiente`, `En proceso`, `Respondido` o `Cerrado`, junto con la fecha límite de respuesta.

> Si ingresas datos incorrectos varias veces seguidas, el sistema bloqueará temporalmente los intentos desde tu conexión por seguridad.

---

## Para el personal del panel

### Acceso

Ingresa a `/panel/login/` con tu usuario y contraseña. Solo los usuarios con permiso de **staff** pueden acceder al panel.

---

### Dashboard (`/panel/`)

Muestra un resumen en tiempo real:

| Indicador | Descripción |
|---|---|
| Total de reclamos | Todos los registrados en el sistema |
| Pendientes | Sin atender aún |
| En proceso | En atención |
| Respondidos / Cerrados | Finalizados |
| Vencidos | Superaron la fecha límite sin respuesta |
| Por vencer | Vencen en los próximos 3 días |

También muestra un desglose por sala y los 8 reclamos más recientes.

---

### Listado de reclamos (`/panel/reclamos/`)

Permite buscar y filtrar todos los reclamos registrados.

**Filtros disponibles:**
- Texto libre (código, nombre, documento, email)
- Sala
- Estado
- Tipo (reclamo / queja)
- Rango de fechas (desde / hasta)
- Solo vencidos

**Exportar a CSV**: haz clic en el botón **Exportar CSV** para descargar los reclamos filtrados. El archivo incluye todos los campos y está protegido contra inyección de fórmulas.

---

### Detalle y gestión de un reclamo

Haz clic en cualquier reclamo del listado para ver su ficha completa.

Desde aquí puedes:

1. **Cambiar el estado**: `Pendiente` → `En proceso` → `Respondido` → `Cerrado`.
2. **Asignar** el reclamo a un usuario del equipo.
3. **Registrar acciones adoptadas** (uso interno, no se envía al consumidor).
4. **Redactar la respuesta** al consumidor.
5. **Agregar una nota interna** que quedará en el historial.
6. **Notificar al consumidor**: al marcar como `Respondido` o `Cerrado`, puedes activar el envío automático de la respuesta por correo.

> Para marcar un reclamo como `Respondido` o `Cerrado` es obligatorio haber escrito la respuesta al consumidor.

El **historial de seguimiento** al final de la página muestra todos los cambios de estado con fecha, usuario y nota.

---

### Gestión de salas (`/panel/salas/`)

Cada sala representa un local físico con su propio libro de reclamaciones.

**Campos de una sala:**
| Campo | Descripción |
|---|---|
| Código | Identificador corto usado en el correlativo y la URL (ej. `MIR`). No se puede cambiar si ya hay reclamos. |
| Nombre | Nombre del local |
| Dirección | Dirección física |
| Distrito | Distrito (opcional) |
| Correo de notificación | Recibe un aviso cada vez que se registra un reclamo en esta sala |
| Activa | Si está desactivada, no aparece en el front público |

Desde el listado también puedes:
- **Editar** una sala existente.
- **Ver el QR** listo para imprimir, apuntando a `/libro/<codigo>/`.
- **Eliminar** una sala (solo si no tiene reclamos registrados).

---

### Gestión de feriados (`/panel/feriados/`)

Los feriados se usan para calcular correctamente la fecha límite de respuesta en días hábiles (se excluyen sábados, domingos y los feriados registrados aquí).

- Agrega los feriados nacionales y locales del año.
- Puedes agregar una descripción (ej. "Fiestas Patrias").

---

### Gestión de usuarios (`/panel/usuarios/`)

Administra los usuarios que tienen acceso al panel.

**Campos:**
| Campo | Descripción |
|---|---|
| Usuario | Nombre de usuario para el login |
| Nombre / Apellido | Nombre completo |
| Correo | Correo del usuario (recibe el correo de prueba SMTP) |
| Activo | Si está desactivado, no puede iniciar sesión |
| Es staff | Debe estar marcado para acceder al panel |
| Contraseña | Dejar en blanco para no cambiarla al editar |

> No puedes eliminar tu propio usuario desde el panel.

---

### Configuración general (`/panel/configuracion/`)

Permite ajustar los datos de la empresa y el correo saliente sin tocar el código.

**Datos de la empresa:**
- Razón social, nombre comercial, RUC, domicilio fiscal.
- Plazo de respuesta en días hábiles (por defecto 15). **Verificar con el área legal.**

**Configuración SMTP:**
- Servidor, puerto, usuario, contraseña, TLS y correo remitente.
- Usa el botón **Enviar correo de prueba** para verificar que la configuración funciona antes de ponerla en producción.

> Si el campo "Servidor SMTP" está vacío, el sistema imprime los correos en la consola del servidor (modo desarrollo).

---

### Tema del panel

El panel tiene modo **oscuro** (por defecto) y modo **claro** (azul cielo). Haz clic en el ícono ☀️ / 🌙 en la barra superior para cambiar. La preferencia se guarda en el navegador.

---

## Preguntas frecuentes

**¿Cuánto tiempo tiene el establecimiento para responder?**
El plazo legal es de 15 días hábiles desde el registro (configurable). La fecha límite exacta aparece en tu constancia.

**¿Puedo registrar más de un reclamo?**
Sí, cada reclamo genera un código único independiente.

**¿Qué diferencia hay entre un reclamo y una queja?**
- **Reclamo**: disconformidad con el producto o servicio recibido.
- **Queja**: malestar por la atención del personal o las instalaciones, sin que implique una disconformidad con el producto/servicio.

**¿Qué hago si no recibo el correo de constancia?**
Revisa la carpeta de spam. Si no aparece, usa la opción de consulta en `/consulta/` con tu código y número de documento para verificar que el reclamo fue registrado.

**¿Puedo modificar mi reclamo después de enviarlo?**
No. Una vez enviado, el reclamo queda registrado y no puede ser modificado por el consumidor. Si hay un error, comunícate directamente con el establecimiento.
