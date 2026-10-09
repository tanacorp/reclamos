from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),  # administración de salas, feriados y usuarios
    path("", include("reclamaciones.urls")),
]
