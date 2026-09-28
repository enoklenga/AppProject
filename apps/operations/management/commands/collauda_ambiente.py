import json
from dataclasses import asdict, dataclass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import NoReverseMatch, reverse

from apps.operations.models import (
    AuditLog,
    Importazione,
    InvioPromemoria,
    PeriodoMensile,
)
from apps.projects.models import (
    Assegnazione,
    Cliente,
    Commessa,
    TariffaAssegnazione,
)
from apps.timesheets.models import RigaOre, SpesaTrasferta


@dataclass
class Controllo:
    nome: str
    esito: str
    dettaglio: str


class Command(BaseCommand):
    help = (
        "Esegue un collaudo non distruttivo di database, migrazioni, "
        "utenti, dati e URL principali."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Restituisce il risultato in formato JSON.",
        )

    def handle(self, *args, **options):
        controlli: list[Controllo] = []
        errori = 0
        avvisi = 0

        def aggiungi(nome, esito, dettaglio):
            nonlocal errori, avvisi
            controlli.append(
                Controllo(
                    nome=nome,
                    esito=esito,
                    dettaglio=str(dettaglio),
                )
            )
            if esito == "ERRORE":
                errori += 1
            elif esito == "AVVISO":
                avvisi += 1

        # Database.
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database(), current_user, "
                    "version()"
                )
                database, utente, versione = cursor.fetchone()
        except Exception as exc:
            aggiungi("database", "ERRORE", exc)
        else:
            aggiungi(
                "database",
                "OK",
                f"{database} – {utente} – {versione.split(',')[0]}",
            )

        # Migrations.
        try:
            executor = MigrationExecutor(connection)
            piano = executor.migration_plan(
                executor.loader.graph.leaf_nodes()
            )
        except Exception as exc:
            aggiungi("migrazioni", "ERRORE", exc)
        else:
            if piano:
                dettagli = ", ".join(
                    f"{migration.app_label}.{migration.name}"
                    for migration, _ in piano
                )
                aggiungi(
                    "migrazioni",
                    "ERRORE",
                    f"Migrazioni non applicate: {dettagli}",
                )
            else:
                aggiungi("migrazioni", "OK", "Allineate")

        User = get_user_model()

        # Critical account availability.
        admin_attivi = User.objects.filter(
            ruolo=User.Ruolo.ADMIN,
            is_active=True,
        ).count()
        if admin_attivi == 0:
            aggiungi(
                "admin_attivi",
                "ERRORE",
                "Non esiste alcun Admin LEF attivo.",
            )
        else:
            aggiungi(
                "admin_attivi",
                "OK",
                f"{admin_attivi} account Admin LEF attivi",
            )

        consulenti_attivi = User.objects.filter(
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        ).count()
        aggiungi(
            "consulenti_attivi",
            "OK" if consulenti_attivi else "AVVISO",
            f"{consulenti_attivi} consulenti attivi",
        )

        # Database counts useful after a restore.
        conteggi = {
            "utenti": User.objects.count(),
            "clienti": Cliente.objects.count(),
            "commesse": Commessa.objects.count(),
            "assegnazioni": Assegnazione.objects.count(),
            "tariffe": TariffaAssegnazione.objects.count(),
            "righe_ore": RigaOre.objects.count(),
            "spese": SpesaTrasferta.objects.count(),
            "periodi": PeriodoMensile.objects.count(),
            "audit": AuditLog.objects.count(),
            "importazioni": Importazione.objects.count(),
            "promemoria": InvioPromemoria.objects.count(),
        }
        aggiungi(
            "conteggi_database",
            "OK",
            json.dumps(conteggi, ensure_ascii=False),
        )

        # Referential sanity checks.
        ore_senza_assegnazione = RigaOre.objects.filter(
            assegnazione__isnull=True
        ).count()
        spese_senza_assegnazione = SpesaTrasferta.objects.filter(
            assegnazione__isnull=True
        ).count()
        if ore_senza_assegnazione or spese_senza_assegnazione:
            aggiungi(
                "integrita_riferimenti",
                "ERRORE",
                (
                    f"Ore senza assegnazione: {ore_senza_assegnazione}; "
                    f"spese senza assegnazione: "
                    f"{spese_senza_assegnazione}"
                ),
            )
        else:
            aggiungi(
                "integrita_riferimenti",
                "OK",
                "Nessuna riga orfana rilevata.",
            )

        # Main application routes.
        route_names = [
            "home",
            "login",
            "health",
            "health_ready",
            "timesheets:ore-list",
            "timesheets:spesa-list",
            "operations:dashboard-admin",
            "operations:periodo-detail",
            "operations:promemoria",
            "operations:importazione-list",
            "operations:audit-list",
            "operations:report-mensile",
        ]
        route_errors = []
        for name in route_names:
            try:
                reverse(name)
            except NoReverseMatch as exc:
                route_errors.append(f"{name}: {exc}")

        if route_errors:
            aggiungi(
                "url_principali",
                "ERRORE",
                " | ".join(route_errors),
            )
        else:
            aggiungi(
                "url_principali",
                "OK",
                f"{len(route_names)} URL risolti correttamente",
            )

        risultato = {
            "esito": "ERRORE" if errori else "OK",
            "errori": errori,
            "avvisi": avvisi,
            "controlli": [asdict(controllo) for controllo in controlli],
        }

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    risultato,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            for controllo in controlli:
                if controllo.esito == "OK":
                    stile = self.style.SUCCESS
                elif controllo.esito == "AVVISO":
                    stile = self.style.WARNING
                else:
                    stile = self.style.ERROR

                self.stdout.write(
                    stile(
                        f"[{controllo.esito}] "
                        f"{controllo.nome}: "
                        f"{controllo.dettaglio}"
                    )
                )

            self.stdout.write("")
            self.stdout.write(
                (
                    f"Risultato: {risultato['esito']} – "
                    f"{errori} errori, {avvisi} avvisi."
                )
            )

        if errori:
            raise SystemExit(1)
