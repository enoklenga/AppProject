from datetime import date

import django.db.models.deletion
from django.db import migrations, models


GO_LIVE_DATE = date(2026, 9, 24)


def align_legacy_planning(apps, schema_editor):
    GiornoPianificato = apps.get_model("planning", "GiornoPianificato")
    RigaOre = apps.get_model("timesheets", "RigaOre")

    legacy = GiornoPianificato.objects.filter(
        data__lt=GO_LIVE_DATE,
        stato_sessione="PIANIFICATA",
    ).order_by("data", "id")

    for sessione in legacy.iterator():
        righe = list(
            RigaOre.objects.filter(
                assegnazione_id=sessione.assegnazione_id,
                data=sessione.data,
                ore=sessione.ore_pianificate,
                tipo_attivita=sessione.tipo_attivita,
            ).order_by("created_at", "id")[:2]
        )

        # Colleghiamo soltanto un match univoco e semanticamente identico.
        # In ogni altro caso preserviamo lo storico come esente, senza fingere
        # una conferma effettuata dall'utente.
        if len(righe) == 1 and not GiornoPianificato.objects.filter(
            riga_ore_generata_id=righe[0].id
        ).exclude(pk=sessione.pk).exists():
            sessione.stato_sessione = "STORICO_ALLINEATO"
            sessione.riga_ore_generata_id = righe[0].id
            sessione.save(update_fields=["stato_sessione", "riga_ore_generata"])
        else:
            sessione.stato_sessione = "STORICO_ESENTE"
            sessione.save(update_fields=["stato_sessione"])

    # Hardening pre-constraint: se il database contiene una conferma parziale
    # creata durante una release intermedia, non lasciamo che la nuova CHECK
    # migration fallisca. Non attribuiamo mai una conferma all'utente.
    incoerenti = GiornoPianificato.objects.filter(
        stato_sessione="CONFERMATA",
    ).filter(
        models.Q(confermata_il__isnull=True)
        | models.Q(confermata_da__isnull=True)
        | models.Q(riga_ore_generata__isnull=True)
    )
    for sessione in incoerenti.iterator():
        if sessione.data < GO_LIVE_DATE and sessione.riga_ore_generata_id:
            sessione.stato_sessione = "STORICO_ALLINEATO"
        elif sessione.data < GO_LIVE_DATE:
            sessione.stato_sessione = "STORICO_ESENTE"
        else:
            sessione.stato_sessione = "PIANIFICATA"
            sessione.riga_ore_generata_id = None
        sessione.confermata_il = None
        sessione.confermata_da_id = None
        sessione.save(
            update_fields=[
                "stato_sessione",
                "riga_ore_generata",
                "confermata_il",
                "confermata_da",
            ]
        )


def reverse_alignment(apps, schema_editor):
    GiornoPianificato = apps.get_model("planning", "GiornoPianificato")
    GiornoPianificato.objects.filter(
        stato_sessione__in=("STORICO_ALLINEATO", "STORICO_ESENTE")
    ).update(
        stato_sessione="PIANIFICATA",
        riga_ore_generata=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0002_session_confirmation"),
        ("timesheets", "0002_rigaore_approvata_da_rigaore_data_approvazione_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="giornopianificato",
            name="stato_sessione",
            field=models.CharField(
                choices=[
                    ("PIANIFICATA", "Pianificata"),
                    ("CONFERMATA", "Conclusa e confermata"),
                    ("STORICO_ALLINEATO", "Storico allineato al timesheet"),
                    ("STORICO_ESENTE", "Storico precedente al go-live"),
                ],
                db_index=True,
                default="PIANIFICATA",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="giornopianificato",
            name="riga_ore_generata",
            field=models.OneToOneField(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sessione_agenda",
                to="timesheets.rigaore",
            ),
        ),
        migrations.RunPython(align_legacy_planning, reverse_alignment),
        migrations.AddConstraint(
            model_name="giornopianificato",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        stato_sessione="PIANIFICATA",
                        confermata_il__isnull=True,
                        confermata_da__isnull=True,
                        riga_ore_generata__isnull=True,
                    )
                    | models.Q(
                        stato_sessione="CONFERMATA",
                        confermata_il__isnull=False,
                        confermata_da__isnull=False,
                        riga_ore_generata__isnull=False,
                    )
                    | models.Q(
                        stato_sessione="STORICO_ALLINEATO",
                        confermata_il__isnull=True,
                        confermata_da__isnull=True,
                        riga_ore_generata__isnull=False,
                    )
                    | models.Q(
                        stato_sessione="STORICO_ESENTE",
                        confermata_il__isnull=True,
                        confermata_da__isnull=True,
                        riga_ore_generata__isnull=True,
                    )
                ),
                name="giorno_pianificato_stato_coerente",
            ),
        ),
    ]
