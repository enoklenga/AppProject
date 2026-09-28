import io
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from openpyxl import Workbook

from apps.operations.import_services import (
    conferma_importazione,
    prepara_importazione,
    serializza_anteprima,
)
from apps.operations.models import (
    AuditLog,
    Importazione,
)
from apps.phases.models import FaseCommessa
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
)
from apps.timesheets.models import (
    RigaOre,
    SpesaTrasferta,
)

User = get_user_model()


class ImportAuditTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-test@example.com",
            password="Password-test-123",
            ruolo=User.Ruolo.ADMIN,
            is_staff=True,
        )

        self.consulente = User.objects.create_user(
            email="consulente-test@example.com",
            password="Password-test-123",
        )

        self.cliente = Cliente.objects.create(
            ragione_sociale="Cliente Import",
            partita_iva="IT00000000071",
        )

        self.commessa = Commessa.objects.create(
            cliente=self.cliente,
            codice="IMP-001",
            descrizione="Test importazione",
            data_inizio=date(2026, 1, 1),
        )

        # La fase di sistema viene creata automaticamente
        # insieme alla commessa.
        self.fase = FaseCommessa.objects.get(
            commessa=self.commessa,
            sistema=True,
        )

        self.assegnazione = Assegnazione.objects.create(
            consulente=self.consulente,
            commessa=self.commessa,
            fase=self.fase,
            ore_previste=100,
            data_inizio=date(2026, 1, 1),
        )

    # =====================================================
    # HELPER
    # =====================================================

    def crea_xlsx(
        self,
        intestazioni,
        righe,
    ):
        workbook = Workbook()
        worksheet = workbook.active

        worksheet.append(
            intestazioni
        )

        for riga in righe:
            worksheet.append(
                riga
            )

        output = io.BytesIO()
        workbook.save(
            output
        )

        return output.getvalue()

    # =====================================================
    # IMPORT ORE
    # =====================================================

    def test_import_ore_valido_con_anteprima_e_conferma(self):
        contenuto = self.crea_xlsx(
            [
                "consulente_email",
                "codice_commessa",
                "fase",
                "data",
                "tipo_attivita",
                "ore",
                "nota",
            ],
            [
                [
                    self.consulente.email,
                    self.commessa.codice,
                    self.fase.nome,
                    "2026-07-10",
                    "CONSULENZA",
                    6,
                    "Analisi iniziale",
                ]
            ],
        )

        anteprima = prepara_importazione(
            attore=self.admin,
            tipo_importazione="ORE",
            nome_file="ore.xlsx",
            contenuto=contenuto,
        )

        self.assertEqual(
            anteprima.importazione.stato,
            Importazione.Stato.PRONTA,
        )

        self.assertEqual(
            len(
                anteprima.righe_valide
            ),
            1,
        )

        conferma_importazione(
            attore=self.admin,
            importazione=(
                anteprima.importazione
            ),
            dati_sessione=(
                serializza_anteprima(
                    anteprima
                )
            ),
        )

        riga = RigaOre.objects.get()

        self.assertEqual(
            riga.ore,
            6,
        )

        self.assertEqual(
            riga.assegnazione,
            self.assegnazione,
        )

        self.assertEqual(
            riga.assegnazione.fase,
            self.fase,
        )

        self.assertTrue(
            riga.bloccata_per_consulente
        )

        self.assertTrue(
            AuditLog.objects.filter(
                entita="RigaOre",
                azione="INSERIMENTO_ADMIN",
            ).exists()
        )

    # =====================================================
    # ERRORE CONSULENTE
    # =====================================================

    def test_file_con_email_errata_non_e_pronto(self):
        contenuto = self.crea_xlsx(
            [
                "consulente_email",
                "codice_commessa",
                "fase",
                "data",
                "tipo_attivita",
                "ore",
            ],
            [
                [
                    "inesistente@example.com",
                    self.commessa.codice,
                    self.fase.nome,
                    "2026-07-10",
                    "CONSULENZA",
                    4,
                ]
            ],
        )

        anteprima = prepara_importazione(
            attore=self.admin,
            tipo_importazione="ORE",
            nome_file="errore.xlsx",
            contenuto=contenuto,
        )

        self.assertEqual(
            anteprima.importazione.stato,
            Importazione.Stato.ERRORE,
        )

        self.assertEqual(
            len(
                anteprima.errori
            ),
            1,
        )

        self.assertEqual(
            RigaOre.objects.count(),
            0,
        )

    # =====================================================
    # IMPORT SPESE
    # =====================================================

    def test_import_spesa_valido(self):
        contenuto = self.crea_xlsx(
            [
                "consulente_email",
                "codice_commessa",
                "fase",
                "data",
                "categoria",
                "importo",
                "nota",
            ],
            [
                [
                    self.consulente.email,
                    self.commessa.codice,
                    self.fase.nome,
                    "2026-07-11",
                    "VIAGGIO",
                    "25,50",
                    "Pedaggio",
                ]
            ],
        )

        anteprima = prepara_importazione(
            attore=self.admin,
            tipo_importazione="SPESE",
            nome_file="spese.xlsx",
            contenuto=contenuto,
        )

        self.assertEqual(
            anteprima.importazione.stato,
            Importazione.Stato.PRONTA,
        )

        conferma_importazione(
            attore=self.admin,
            importazione=(
                anteprima.importazione
            ),
            dati_sessione=(
                serializza_anteprima(
                    anteprima
                )
            ),
        )

        spesa = (
            SpesaTrasferta
            .objects
            .get()
        )

        self.assertEqual(
            spesa.importo,
            Decimal("25.50"),
        )

        self.assertEqual(
            spesa.assegnazione,
            self.assegnazione,
        )

        self.assertEqual(
            spesa.assegnazione.fase,
            self.fase,
        )

        self.assertTrue(
            spesa.bloccata_per_consulente
        )

    # =====================================================
    # DUPLICATI
    # =====================================================

    def test_file_completato_non_puo_essere_reimportato(self):
        contenuto = self.crea_xlsx(
            [
                "consulente_email",
                "codice_commessa",
                "fase",
                "data",
                "tipo_attivita",
                "ore",
            ],
            [
                [
                    self.consulente.email,
                    self.commessa.codice,
                    self.fase.nome,
                    "2026-07-12",
                    "FORMAZIONE",
                    4,
                ]
            ],
        )

        anteprima = prepara_importazione(
            attore=self.admin,
            tipo_importazione="ORE",
            nome_file="duplicato.xlsx",
            contenuto=contenuto,
        )

        self.assertEqual(
            anteprima.importazione.stato,
            Importazione.Stato.PRONTA,
        )

        conferma_importazione(
            attore=self.admin,
            importazione=(
                anteprima.importazione
            ),
            dati_sessione=(
                serializza_anteprima(
                    anteprima
                )
            ),
        )

        anteprima.importazione.refresh_from_db()

        self.assertEqual(
            anteprima.importazione.stato,
            Importazione.Stato.COMPLETATA,
        )

        with self.assertRaisesMessage(
            Exception,
            "già importato",
        ):
            prepara_importazione(
                attore=self.admin,
                tipo_importazione="ORE",
                nome_file="duplicato.xlsx",
                contenuto=contenuto,
            )