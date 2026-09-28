from datetime import date
from decimal import Decimal

from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.timesheets.models import RigaOre, SpesaTrasferta


class ApiBaseTests(APITestCase):
    password = "Password-test-API-123"

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-api@example.com",
            password=self.password,
            ruolo=User.Ruolo.ADMIN,
            is_active=True,
        )
        self.consulente = User.objects.create_user(
            email="consulente-api@example.com",
            password=self.password,
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        )
        self.pm = User.objects.create_user(
            email="pm-api@example.com",
            password=self.password,
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        )
        self.altro = User.objects.create_user(
            email="altro-api@example.com",
            password=self.password,
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        )

        self.cliente_gestito = Cliente.objects.create(
            ragione_sociale="Cliente gestito",
            partita_iva="00000000001",
        )
        self.cliente_altro = Cliente.objects.create(
            ragione_sociale="Cliente non gestito",
            partita_iva="00000000002",
        )

        self.commessa_gestita = Commessa.objects.create(
            cliente=self.cliente_gestito,
            codice="API-GESTITA",
            descrizione="Commessa gestita dal PM",
            ore_budget=100,
            data_inizio=date(2026, 1, 1),
        )
        self.commessa_altra = Commessa.objects.create(
            cliente=self.cliente_altro,
            codice="API-ALTRA",
            descrizione="Commessa non visibile",
            ore_budget=100,
            data_inizio=date(2026, 1, 1),
        )

        self.assegnazione_pm = Assegnazione.objects.create(
            consulente=self.pm,
            commessa=self.commessa_gestita,
            ore_previste=20,
            ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER,
            data_inizio=date(2026, 1, 1),
        )
        self.assegnazione_consulente = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa_gestita,
            ore_previste=50,
            data_inizio=date(2026, 1, 1),
        )
        self.assegnazione_altra = Assegnazione.objects.create(
            consulente=self.altro,
            commessa=self.commessa_altra,
            ore_previste=50,
            data_inizio=date(2026, 1, 1),
        )

        self.ore_consulente = RigaOre.objects.create(
            assegnazione=self.assegnazione_consulente,
            data=date(2026, 7, 1),
            tipo_attivita="CONSULENZA",
            ore=4,
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )
        self.ore_altra = RigaOre.objects.create(
            assegnazione=self.assegnazione_altra,
            data=date(2026, 7, 2),
            tipo_attivita="CONSULENZA",
            ore=5,
            inserita_da=self.altro,
            ultima_modifica_da=self.altro,
        )
        self.spesa_consulente = SpesaTrasferta.objects.create(
            assegnazione=self.assegnazione_consulente,
            data=date(2026, 7, 1),
            categoria=SpesaTrasferta.Categoria.VIAGGIO,
            importo=Decimal("25.00"),
            inserita_da=self.consulente,
            ultima_modifica_da=self.consulente,
        )

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )

    def ids_from_paginated_response(self, response):
        return {item["id"] for item in response.data["results"]}

    def test_health_is_public(self):
        response = self.client.get(reverse("api:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")

    def test_api_root_requires_authentication(self):
        response = self.client.get(reverse("api:root"))
        self.assertEqual(response.status_code, 401)

    def test_token_login_and_logout(self):
        response = self.client.post(
            reverse("api:token-login"),
            {
                "email": self.consulente.email,
                "password": self.password,
            },
        )
        self.assertEqual(response.status_code, 200)
        token = response.data["token"]

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token}"
        )
        me = self.client.get(reverse("api:me"))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["email"], self.consulente.email)

        logout = self.client.post(reverse("api:token-logout"))
        self.assertEqual(logout.status_code, 204)
        self.assertFalse(
            Token.objects.filter(user=self.consulente).exists()
        )

    def test_consultant_sees_only_own_timesheet(self):
        self.authenticate(self.consulente)
        response = self.client.get(reverse("api:ore-list"))

        self.assertEqual(response.status_code, 200)
        ids = self.ids_from_paginated_response(response)
        self.assertIn(str(self.ore_consulente.id), ids)
        self.assertNotIn(str(self.ore_altra.id), ids)

    def test_pm_sees_team_data_on_managed_project_only(self):
        self.authenticate(self.pm)
        response = self.client.get(reverse("api:ore-list"))

        self.assertEqual(response.status_code, 200)
        ids = self.ids_from_paginated_response(response)
        self.assertIn(str(self.ore_consulente.id), ids)
        self.assertNotIn(str(self.ore_altra.id), ids)

        me = self.client.get(reverse("api:me"))
        self.assertTrue(me.data["project_manager"])

    def test_admin_sees_all_timesheet_rows(self):
        self.authenticate(self.admin)
        response = self.client.get(reverse("api:ore-list"))

        self.assertEqual(response.status_code, 200)
        ids = self.ids_from_paginated_response(response)
        self.assertIn(str(self.ore_consulente.id), ids)
        self.assertIn(str(self.ore_altra.id), ids)

    def test_api_resources_are_read_only(self):
        self.authenticate(self.admin)
        response = self.client.post(
            reverse("api:cliente-list"),
            {
                "ragione_sociale": "Non consentito",
                "partita_iva": "00000000003",
            },
        )
        self.assertEqual(response.status_code, 405)

    def test_date_filter(self):
        self.authenticate(self.admin)
        response = self.client.get(
            reverse("api:ore-list"),
            {"data_da": "2026-07-02"},
        )
        self.assertEqual(response.status_code, 200)
        ids = self.ids_from_paginated_response(response)
        self.assertNotIn(str(self.ore_consulente.id), ids)
        self.assertIn(str(self.ore_altra.id), ids)
