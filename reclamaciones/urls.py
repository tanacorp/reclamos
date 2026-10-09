from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "reclamaciones"

urlpatterns = [
    # Front público
    path("", RedirectView.as_view(pattern_name="reclamaciones:consulta", permanent=False), name="inicio"),
    path("libro/<slug:sala_codigo>/", views.HojaReclamacionView.as_view(), name="hoja"),
    path("constancia/<str:token>/", views.ConstanciaView.as_view(), name="constancia"),
    path("consulta/", views.ConsultaView.as_view(), name="consulta"),

    # Panel — autenticación
    path("panel/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("panel/logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Panel — reclamos
    path("panel/", views.PanelView.as_view(), name="panel"),
    path("panel/reclamos/", views.ListaReclamosView.as_view(), name="lista"),
    path("panel/reclamos/exportar/", views.ExportarCSVView.as_view(), name="exportar"),
    path("panel/reclamos/<int:pk>/", views.DetalleReclamoView.as_view(), name="detalle"),

    # Panel — configuración: salas
    path("panel/salas/", views.SalasView.as_view(), name="salas"),
    path("panel/salas/nueva/", views.SalaNuevaView.as_view(), name="sala_nueva"),
    path("panel/salas/<int:pk>/", views.SalasView.as_view(), name="sala_editar"),
    path("panel/salas/<int:pk>/qr/", views.SalaQRView.as_view(), name="sala_qr"),
    path("panel/salas/<int:pk>/eliminar/", views.SalaEliminarView.as_view(), name="sala_eliminar"),

    # Panel — configuración: feriados
    path("panel/feriados/", views.FeriadosView.as_view(), name="feriados"),
    path("panel/feriados/nuevo/", views.FeriadoNuevoView.as_view(), name="feriado_nuevo"),
    path("panel/feriados/<int:pk>/", views.FeriadosView.as_view(), name="feriado_editar"),
    path("panel/feriados/<int:pk>/eliminar/", views.FeriadoEliminarView.as_view(), name="feriado_eliminar"),

    # Panel — configuración: usuarios
    path("panel/usuarios/", views.UsuariosView.as_view(), name="usuarios"),
    path("panel/usuarios/nuevo/", views.UsuarioNuevoView.as_view(), name="usuario_nuevo"),
    path("panel/usuarios/<int:pk>/", views.UsuariosView.as_view(), name="usuario_editar"),
    path("panel/usuarios/<int:pk>/eliminar/", views.UsuarioEliminarView.as_view(), name="usuario_eliminar"),

    # Panel — configuración general
    path("panel/configuracion/", views.ConfiguracionView.as_view(), name="configuracion"),
    path("panel/configuracion/test-correo/", views.TestCorreoView.as_view(), name="test_correo"),
]
