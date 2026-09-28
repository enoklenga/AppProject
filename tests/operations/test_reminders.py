from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.operations.models import (
    ConfigurazionePromemoria,
    InvioPromemoria,
    PeriodoMensile,
)
from apps.operations.services import (
    consulenti_senza_ore,
    invia_promemoria,
)
from apps.projects.models import Assegnazione, Cliente, Commessa
from apps.timesheets.models import RigaOre

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="timesheet-test@example.com",
    SITE_URL="http://testserver",
)
class ReminderTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_staff=True,
        )
        self.consulente_senza_ore = User.objects.create_user(
            email="senza-ore@example.com",
            password="Password-test-123",
        )
        self.consulente_con_ore = User.objects.create_user(
            email="con-ore@example.com",
            password="Password-test-123",
        )
        self.consulente_inattivo = User.objects.create_user(
            email="inattivo@example.com",
            password="Password-test-123",
            is_active=False,
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Promemoria",
            partita_iva="IT00000000061",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="REM-001",
            descrizione="Test promemoria",
            data_inizio=date(2026, 1, 1),
        )
        self.ass_senza = Assegnazione.objects.create(
            consulente=self.consulente_senza_ore,
            commessa=self.commessa,
            ore_previste=40,
            data_inizio=date(2026, 1, 1),
        )
        self.ass_con = Assegnazione.objects.create(
            consulente=self.consulente_con_ore,
            commessa=self.commessa,
            ore_previste=40,
            data_inizio=date(2026, 1, 1),
        )
        self.ass_inattivo = Assegnazione.objects.create(
            consulente=self.consulente_inattivo,
            commessa=self.commessa,
            ore_previste=40,
            data_inizio=date(2026, 1, 1),
        )
        RigaOre.objects.create(
            assegnazione=self.ass_con,
            data=date(2026, 7, 10),
            tipo_attivita="CONSULENZA",
            ore=4,
            inserita_da=self.consulente_con_ore,
            ultima_modifica_da=self.consulente_con_ore,
        )
        self.configurazione = ConfigurazionePromemoria.objects.create(
            giorno_invio=25,
            ora_invio=time(9, 0),
            attiva=True,
            solo_assenza_totale_ore=True,
            aggiornata_da=self.admin,
        )

    def test_anteprima_include_solo_attivi_senza_ore(self):
        destinatari = consulenti_senza_ore(anno=2026, mese=7)

        self.assertEqual(len(destinatari), 1)
        self.assertEqual(
            destinatari[0].consulente,
            self.consulente_senza_ore,
        )

    def test_invio_crea_email_e_registro(self):
        esito = invia_promemoria(
            configurazione=self.configurazione,
            anno=2026,
            mese=7,
            forza=True,
        )

        self.assertEqual(esito.inviati, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].to,
            [self.consulente_senza_ore.email],
        )
        self.assertTrue(
            InvioPromemoria.objects.filter(
                consulente=self.consulente_senza_ore,
                anno=2026,
                mese=7,
                stato=InvioPromemoria.Stato.INVIATO,
            ).exists()
        )

    def test_secondo_invio_non_duplica_email(self):
        invia_promemoria(
            configurazione=self.configurazione,
            anno=2026,
            mese=7,
            forza=True,
        )
        esito = invia_promemoria(
            configurazione=self.configurazione,
            anno=2026,
            mese=7,
            forza=True,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(esito.saltati, 1)

    def test_periodo_chiuso_blocca_promemoria(self):
        PeriodoMensile.objects.create(
            anno=2026,
            mese=7,
            stato=PeriodoMensile.Stato.CHIUSO,
            chiuso_da=self.admin,
            data_chiusura=timezone.now(),
        )

        esito = invia_promemoria(
            configurazione=self.configurazione,
            anno=2026,
            mese=7,
            forza=True,
        )

        self.assertEqual(esito.inviati, 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("chiuso", esito.motivo_salto.lower())

    def test_consulente_non_accede_alla_pagina(self):
        self.client.force_login(self.consulente_senza_ore)
        response = self.client.get(reverse("operations:promemoria"))

        self.assertEqual(response.status_code, 403)

    def test_admin_visualizza_anteprima(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("operations:promemoria"),
            {"mese": "2026-07"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            self.consulente_senza_ore.email,
        )
        self.assertNotContains(
            response,
            self.consulente_con_ore.email,
        )
