import ast
import json

from django import template

register = template.Library()


LABELS = {
    "consulente_email": "Consulente",
    "codice_commessa": "Commessa",
    "tipo_attivita": "Tipo attività",
    "categoria": "Categoria",
    "data": "Data",
    "ore": "Ore",
    "importo": "Importo",
    "nota": "Nota",
    "stato": "Stato",
    "azione": "Azione",
    "motivazione": "Motivazione",
    "utente": "Utente",
    "email": "Email",
    "telefono": "Telefono",
    "ragione_sociale": "Ragione sociale",
    "partita_iva": "Partita IVA",
    "ore_previste": "Ore previste",
    "data_inizio": "Data inizio",
    "data_fine": "Data fine",
    "data_fine_prevista": "Data fine prevista",
    "tariffa_oraria": "Tariffa oraria",
    "valida_dal": "Valida dal",
    "created_at": "Data creazione",
    "updated_at": "Ultima modifica",
}


def _parse_value(value):
    """Accept JSONField values, JSON strings and old Python-dict strings."""
    if value is None:
        return None

    if not isinstance(value, str):
        return value

    text = value.strip()

    if not text or text in {"null", "None", "{}", "[]"}:
        return None

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Some older values may have been stored/rendered using Python repr.
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


def _label(key):
    key = str(key)

    if key in LABELS:
        return LABELS[key]

    cleaned = key.replace("_", " ").strip()

    if not cleaned:
        return "Valore"

    if cleaned.lower() == "id":
        return "ID"

    return cleaned[0].upper() + cleaned[1:]


def _scalar(value):
    if value is None or value == "":
        return "—"

    if isinstance(value, bool):
        return "Sì" if value else "No"

    return str(value)


def _flatten(value, rows, prefix=""):
    if isinstance(value, dict):
        if not value:
            return

        for key, child in value.items():
            label = _label(key)
            full_label = f"{prefix} › {label}" if prefix else label

            if isinstance(child, (dict, list, tuple)):
                _flatten(child, rows, full_label)
            else:
                rows.append((full_label, _scalar(child)))

        return

    if isinstance(value, (list, tuple)):
        if not value:
            return

        # Compact primitive lists into one readable value.
        if all(not isinstance(item, (dict, list, tuple)) for item in value):
            rows.append((prefix or "Valori", ", ".join(_scalar(item) for item in value)))
            return

        for index, child in enumerate(value, start=1):
            full_label = f"{prefix} [{index}]" if prefix else f"Voce {index}"
            _flatten(child, rows, full_label)

        return

    rows.append((prefix or "Valore", _scalar(value)))


@register.inclusion_tag("operations/partials/readable_data.html")
def readable_data(value, empty_label="Nessun valore"):
    """
    Render structured values as readable label/value rows instead of raw JSON.
    """
    parsed = _parse_value(value)
    rows = []

    if parsed is not None:
        _flatten(parsed, rows)

    return {
        "rows": rows,
        "empty_label": empty_label,
    }
