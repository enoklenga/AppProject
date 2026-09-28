from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.operations.services import (
    configurazione_promemoria_corrente,
    invia_promemoria,
)


class Command(BaseCommand):
    help = (
        "Controlla la configurazione e invia i promemoria ai consulenti "
        "che non hanno registrato ore nel mese."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--mese",
            help="Mese da controllare nel formato YYYY-MM.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignora giorno e ora configurati.",
        )

    def handle(self, *args, **options):
        configurazione = configurazione_promemoria_corrente()
        if configurazione is None:
            self.stdout.write(
                self.style.WARNING(
                    "Nessuna configurazione presente. Aprire prima "
                    "Controllo > Promemoria dall'interfaccia Admin."
                )
            )
            return

        oggi = timezone.localdate()
        anno = oggi.year
        mese = oggi.month

        valore_mese = options.get("mese")
        if valore_mese:
            try:
                anno_str, mese_str = valore_mese.split("-", 1)
                anno = int(anno_str)
                mese = int(mese_str)
                if not 1 <= mese <= 12:
                    raise ValueError
            except ValueError as exc:
                raise CommandError(
                    "Il parametro --mese deve usare il formato YYYY-MM."
                ) from exc

        esito = invia_promemoria(
            configurazione=configurazione,
            anno=anno,
            mese=mese,
            forza=options["force"],
        )

        if esito.motivo_salto:
            self.stdout.write(
                self.style.WARNING(esito.motivo_salto)
            )
            return

        messaggio = (
            f"Periodo {mese:02d}/{anno}: "
            f"{esito.inviati} inviati, "
            f"{esito.saltati} saltati, "
            f"{esito.errori} errori."
        )
        if esito.errori:
            self.stdout.write(self.style.WARNING(messaggio))
        else:
            self.stdout.write(self.style.SUCCESS(messaggio))
