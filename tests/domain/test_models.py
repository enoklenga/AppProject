from datetime import date, time

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.operations.models import (
    ConfigurazionePromemoria,
    InvioPromemoria,
    PeriodoMensile,
)
from apps.projects.models import Assegnazione, Cliente, Commessa

User = get_user_model()


class VincoliDatabaseTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="password-test",
            ruolo=User.Ruolo.ADMIN,
        )
        self.consulente = User.objects.create_user(
            email="consulente@example.com",
            password="password-test",
        )
        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Test",
            partita_iva="IT12345678901",
        )
        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="TEST-001",
            descrizione="Commessa di test",
            data_inizio=date(2026, 1, 1),
        )

    def test_una_sola_assegnazione_attiva(self):
        Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            ore_previste=40,
            data_inizio=date(2026, 1, 1),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Assegnazione.objects.create(
                    consulente=self.consulente,
                    commessa=self.commessa,
                    ore_previste=20,
                    data_inizio=date(2026, 2, 1),
                )

    def test_periodo_unico_per_mese(self):
        PeriodoMensile.objects.create(anno=2026, mese=7)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PeriodoMensile.objects.create(anno=2026, mese=7)

    def test_promemoria_unico_per_consulente_e_mese(self):
        configurazione = ConfigurazionePromemoria.objects.create(
            giorno_invio=25,
            ora_invio=time(8, 0),
            aggiornata_da=self.admin,
        )
        InvioPromemoria.objects.create(
            configurazione=configurazione,
            consulente=self.consulente,
            anno=2026,
            mese=7,
            stato=InvioPromemoria.Stato.INVIATO,
            data_tentativo="2026-07-25T08:00:00+02:00",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvioPromemoria.objects.create(
                    configurazione=configurazione,
                    consulente=self.consulente,
                    anno=2026,
                    mese=7,
                    stato=InvioPromemoria.Stato.INVIATO,
                    data_tentativo="2026-07-25T09:00:00+02:00",
                )
