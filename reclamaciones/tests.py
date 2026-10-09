from datetime import date

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Feriado, Reclamo, Sala, sumar_dias_habiles

DATOS = {
    "nombres": "Ana", "apellidos": "Pérez", "tipo_documento": "DNI", "numero_documento": "12345678",
    "domicilio": "Jr. Prueba 1", "telefono": "999888777", "email": "ana@example.com",
    "tipo_bien": "SERVICIO", "descripcion_bien": "Máquina tragamonedas", "monto_reclamado": "50.00",
    "tipo": "RECLAMO", "detalle": "La máquina retuvo mi dinero.", "pedido": "Devolución del monto.",
    "acepta_terminos": "on",
}


class DiasHabilesTests(TestCase):
    def test_omite_fin_de_semana_y_feriados(self):
        # lunes 2026-10-05 + 5 días hábiles = lunes 2026-10-12
        self.assertEqual(sumar_dias_habiles(date(2026, 10, 5), 5), date(2026, 10, 12))
        Feriado.objects.create(fecha=date(2026, 10, 8), descripcion="Combate de Angamos")
        self.assertEqual(sumar_dias_habiles(date(2026, 10, 5), 5), date(2026, 10, 13))


class FrontPublicoTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(codigo="MIR", nombre="Sala Miraflores", direccion="Av. 1", email_notificacion="sala@example.com")

    def test_registro_genera_codigo_correlativo_y_correos(self):
        url = reverse("reclamaciones:hoja", args=["MIR"])
        r1 = self.client.post(url, DATOS)
        self.assertEqual(r1.status_code, 302)
        self.client.post(url, DATOS)
        codigos = list(Reclamo.objects.order_by("id").values_list("codigo", flat=True))
        self.assertTrue(codigos[0].startswith("MIR-") and codigos[0].endswith("-000001"))
        self.assertTrue(codigos[1].endswith("-000002"))
        self.assertEqual(len(mail.outbox), 4)  # consumidor + sala, por 2 reclamos
        self.assertIsNotNone(Reclamo.objects.first().fecha_limite)

    def test_constancia_visible_con_token(self):
        r = self.client.post(reverse("reclamaciones:hoja", args=["MIR"]), DATOS, follow=True)
        self.assertContains(r, "Constancia de registro")

    def test_constancia_con_token_invalido(self):
        self.assertEqual(self.client.get(reverse("reclamaciones:constancia", args=["falso"])).status_code, 404)

    def test_validaciones(self):
        url = reverse("reclamaciones:hoja", args=["MIR"])
        malo = {**DATOS, "numero_documento": "123"}
        self.assertEqual(self.client.post(url, malo).status_code, 400)
        menor = {**DATOS, "es_menor_de_edad": "on"}
        self.assertEqual(self.client.post(url, menor).status_code, 400)
        sin_terminos = {k: v for k, v in DATOS.items() if k != "acepta_terminos"}
        self.assertEqual(self.client.post(url, sin_terminos).status_code, 400)
        spam = {**DATOS, "sitio_web": "http://spam"}
        self.assertEqual(self.client.post(url, spam).status_code, 400)
        self.assertEqual(Reclamo.objects.count(), 0)

    def test_sala_inactiva_no_disponible(self):
        Sala.objects.filter(pk=self.sala.pk).update(activa=False)
        self.assertEqual(self.client.get(reverse("reclamaciones:hoja", args=["MIR"])).status_code, 404)

    def test_consulta_por_codigo_y_documento(self):
        self.client.post(reverse("reclamaciones:hoja", args=["MIR"]), DATOS)
        codigo = Reclamo.objects.get().codigo
        ok = self.client.post(reverse("reclamaciones:consulta"), {"codigo": codigo, "numero_documento": "12345678"})
        self.assertContains(ok, codigo)
        mal = self.client.post(reverse("reclamaciones:consulta"), {"codigo": codigo, "numero_documento": "00000000"})
        self.assertContains(mal, "No encontramos")


class PanelTests(TestCase):
    def setUp(self):
        self.sala = Sala.objects.create(codigo="MIR", nombre="Sala Miraflores", direccion="Av. 1")
        User = get_user_model()
        self.staff = User.objects.create_user("gestor", password="clave-segura-123", is_staff=True)
        self.noStaff = User.objects.create_user("cliente", password="clave-segura-123")
        self.client.post(reverse("reclamaciones:hoja", args=["MIR"]), DATOS)
        self.reclamo = Reclamo.objects.get()

    def test_requiere_staff(self):
        for name, args in [("panel", []), ("lista", []), ("exportar", []), ("detalle", [self.reclamo.pk])]:
            resp = self.client.get(reverse(f"reclamaciones:{name}", args=args))
            self.assertIn(resp.status_code, (302, 403), name)
        self.client.force_login(self.noStaff)
        self.assertEqual(self.client.get(reverse("reclamaciones:panel")).status_code, 403)

    def test_panel_lista_y_detalle(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("reclamaciones:panel")), "Panel de gestión")
        self.assertContains(self.client.get(reverse("reclamaciones:lista") + "?estado=PENDIENTE"), self.reclamo.codigo)
        self.assertContains(self.client.get(reverse("reclamaciones:detalle", args=[self.reclamo.pk])), self.reclamo.codigo)

    def test_responder_cambia_estado_y_notifica(self):
        self.client.force_login(self.staff)
        mail.outbox.clear()
        url = reverse("reclamaciones:detalle", args=[self.reclamo.pk])
        sin_respuesta = self.client.post(url, {"estado": "RESPONDIDO", "respuesta": ""})
        self.assertEqual(sin_respuesta.status_code, 400)
        r = self.client.post(url, {"estado": "RESPONDIDO", "respuesta": "Se devolvió el monto.", "notificar_consumidor": "on"})
        self.assertEqual(r.status_code, 302)
        self.reclamo.refresh_from_db()
        self.assertEqual(self.reclamo.estado, "RESPONDIDO")
        self.assertEqual(self.reclamo.respondido_por, self.staff)
        self.assertIsNotNone(self.reclamo.fecha_respuesta)
        self.assertEqual(len(mail.outbox), 1)
        self.assertGreaterEqual(self.reclamo.seguimientos.count(), 2)

    def test_exportar_csv_neutraliza_formulas(self):
        Reclamo.objects.filter(pk=self.reclamo.pk).update(detalle="=HYPERLINK(\"http://x\")")
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("reclamaciones:exportar"))
        body = resp.content.decode("utf-8")
        self.assertIn("'=HYPERLINK", body)
        self.assertIn(self.reclamo.codigo, body)
