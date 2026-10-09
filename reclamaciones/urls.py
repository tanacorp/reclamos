from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "reclamaciones"

urlpatterns = [
    # Front público
    path("", RedirectView.as_view(pattern_name="reclamaciones:consulta", permanent=False), name="inicio"),
    path("libro/<str:ruc>/<slug:sala_codigo>/", views.HojaReclamacionView.as_view(), name="hoja"),
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

    # Panel — empresas
    path("panel/empresas/", views.EmpresasView.as_view(), name="empresas"),
    path("panel/empresas/nueva/", views.EmpresaNuevaView.as_view(), name="empresa_nueva"),
    path("panel/empresas/<int:pk>/", views.EmpresasView.as_view(), name="empresa_editar"),
    path("panel/empresas/<int:pk>/eliminar/", views.EmpresaEliminarView.as_view(), name="empresa_eliminar"),
    path("panel/empresas/<int:pk>/test-correo/", views.TestCorreoEmpresaView.as_view(), name="empresa_test_correo"),

    # Panel — salas
    path("panel/salas/", views.SalasView.as_view(), name="salas"),
    path("panel/salas/nueva/", views.SalaNuevaView.as_view(), name="sala_nueva"),
    path("panel/salas/<int:pk>/", views.SalasView.as_view(), name="sala_editar"),
    path("panel/salas/<int:pk>/qr/", views.SalaQRView.as_view(), name="sala_qr"),
    path("panel/salas/<int:pk>/eliminar/", views.SalaEliminarView.as_view(), name="sala_eliminar"),

    # Panel — feriados
    path("panel/feriados/", views.FeriadosView.as_view(), name="feriados"),
    path("panel/feriados/nuevo/", views.FeriadoNuevoView.as_view(), name="feriado_nuevo"),
    path("panel/feriados/<int:pk>/", views.FeriadosView.as_view(), name="feriado_editar"),
    path("panel/feriados/<int:pk>/eliminar/", views.FeriadoEliminarView.as_view(), name="feriado_eliminar"),

    # Panel — usuarios
    path("panel/usuarios/", views.UsuariosView.as_view(), name="usuarios"),
    path("panel/usuarios/nuevo/", views.UsuarioNuevoView.as_view(), name="usuario_nuevo"),
    path("panel/usuarios/<int:pk>/", views.UsuariosView.as_view(), name="usuario_editar"),
    path("panel/usuarios/<int:pk>/eliminar/", views.UsuarioEliminarView.as_view(), name="usuario_eliminar"),
]
