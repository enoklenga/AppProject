import json
from datetime import date, datetime

from django import template
from django.utils.dateparse import parse_date, parse_datetime


register = template.Library()


FIELD_LABELS = {
    "stato": "Stato",
    "data": "Data",
    "data_chiusura": "Data chiusura",
    "consulente_email": "Consulente",
    "consulente_id": "Consulente",
    "codice_commessa": "Commessa",
    "commessa_id": "Commessa",
    "assegnazione_id": "Assegnazione",
    "tipo_attivita": "Tipo attività",
    "categoria": "Categoria",
    "ore": "Ore",
    "importo": "Importo",
    "nota": "Nota",
    "descrizione": "Descrizione",
    "forzatura_tariffe_mancanti": "Forzatura tariffe mancanti",
}


FIELD_ORDER = {
    "stato": 10,
    "data": 20,
    "data_chiusura": 30,
    "consulente_email": 40,
    "consulente_id": 40,
    "codice_commessa": 50,
    "commessa_id": 50,
    "assegnazione_id": 60,
    "tipo_attivita": 70,
    "categoria": 80,
    "ore": 90,
    "importo": 100,
    "nota": 110,
    "descrizione": 120,
    "forzatura_tariffe_mancanti": 130,
}


VALUE_LABELS = {
    "APERTO": "Aperto",
    "CHIUSO": "Chiuso",
    "ATTIVA": "Attiva",
    "ATTIVO": "Attivo",
    "INATTIVA": "Inattiva",
    "INATTIVO": "Inattivo",
    "INVIATO": "Inviato",
    "ERRORE": "Errore",
    "PRONTA": "Pronta",
    "COMPLETATA": "Completata",
}


def _display_value(value):
    if value is None or value == "":
        return "—"

    if isinstance(value, bool):
        return "Sì" if value else "No"

    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y %H:%M")
        return value.strftime("%d/%m/%Y")

    if isinstance(value, str):
        if value in VALUE_LABELS:
            return VALUE_LABELS[value]

        parsed_datetime = parse_datetime(value)
        if parsed_datetime:
            return parsed_datetime.strftime("%d/%m/%Y %H:%M")

        parsed_date = parse_date(value)
        if parsed_date:
            return parsed_date.strftime("%d/%m/%Y")

        return value

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


@register.filter
def display_json_items(value):
    if not value:
        return []

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return [{
                "label": "Valore",
                "value": value,
            }]

    if not isinstance(value, dict):
        return [{
            "label": "Valore",
            "value": _display_value(value),
        }]

    ordered_items = sorted(
        value.items(),
        key=lambda item: (
            FIELD_ORDER.get(item[0], 999),
            item[0],
        ),
    )

    result = []

    for key, raw_value in ordered_items:
        result.append({
            "label": FIELD_LABELS.get(
                key,
                key.replace("_", " ").capitalize(),
            ),
            "value": _display_value(raw_value),
        })

    return result