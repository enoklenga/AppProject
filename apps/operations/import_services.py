import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook, load_workbook

from apps.common.file_security import validate_import_content
from apps.accounts.models import User
from apps.projects.models import (
    Assegnazione,
    Commessa,
    TariffaAssegnazione,
)
from apps.phases.models import FaseCommessa
from apps.timesheets.models import SpesaTrasferta
from apps.timesheets.services import (
    inserisci_ore,
    inserisci_spesa,
    periodo_chiuso,
)
from .models import (
    ErroreImportazione,
    Importazione,
)


COLONNE_OBBLIGATORIE = {
    "ORE": {
        "consulente_email",
        "codice_commessa",
        "fase",
        "data",
        "tipo_attivita",
        "ore",
    },
    "SPESE": {
        "consulente_email",
        "codice_commessa",
        "fase",
        "data",
        "categoria",
        "importo",
    },
}

COLONNE_TEMPLATE = {
    "ORE": [
        "consulente_email",
        "codice_commessa",
        "fase",
        "data",
        "tipo_attivita",
        "ore",
        "nota",
    ],
    "SPESE": [
        "consulente_email",
        "codice_commessa",
        "fase",
        "data",
        "categoria",
        "importo",
        "nota",
    ],
}


IMPORT_MAX_UPLOAD_SIZE_MB = getattr(settings, "IMPORT_MAX_UPLOAD_SIZE_MB", 5)
IMPORT_MAX_UPLOAD_SIZE_BYTES = IMPORT_MAX_UPLOAD_SIZE_MB * 1024 * 1024


@dataclass(frozen=True)
class RigaAnteprima:
    numero_riga: int
    dati: dict[str, Any]


@dataclass(frozen=True)
class AnteprimaImportazione:
    importazione: Importazione
    tipo_importazione: str
    righe_valide: list[RigaAnteprima]
    errori: list[ErroreImportazione]


class ErroreCommitImportazione(Exception):
    def __init__(self, numero_riga: int, messaggio: str):
        super().__init__(messaggio)
        self.numero_riga = numero_riga
        self.messaggio = messaggio


def _normalizza_header(value: Any) -> str:
    testo = str(value or "").strip().lower()
    testo = re.sub(r"[\s\-\/]+", "_", testo)
    testo = re.sub(r"[^a-z0-9_]", "", testo)
    return testo.strip("_")


def _normalizza_valore(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return value


def _leggi_csv(contenuto: bytes) -> list[dict[str, Any]]:
    try:
        testo = contenuto.decode("utf-8-sig")
    except UnicodeDecodeError:
        testo = contenuto.decode("latin-1")

    campione = testo[:4096]
    try:
        dialect = csv.Sniffer().sniff(
            campione,
            delimiters=",;\t|",
        )
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    reader = csv.reader(io.StringIO(testo), dialect)
    righe = list(reader)
    if not righe:
        return []

    intestazioni = [_normalizza_header(v) for v in righe[0]]
    dati = []
    for valori in righe[1:]:
        if not any(str(v or "").strip() for v in valori):
            continue
        valori_estesi = list(valori) + [""] * (
            len(intestazioni) - len(valori)
        )
        dati.append(
            {
                intestazioni[indice]: _normalizza_valore(valore)
                for indice, valore in enumerate(
                    valori_estesi[: len(intestazioni)]
                )
            }
        )
    return dati


def _leggi_xlsx(contenuto: bytes) -> list[dict[str, Any]]:
    workbook = load_workbook(
        io.BytesIO(contenuto),
        read_only=True,
        data_only=True,
    )
    worksheet = workbook.active
    iterator = worksheet.iter_rows(values_only=True)

    try:
        intestazione = next(iterator)
    except StopIteration:
        return []

    intestazioni = [_normalizza_header(v) for v in intestazione]
    dati = []
    for valori in iterator:
        if not any(str(v or "").strip() for v in valori):
            continue
        valori_estesi = list(valori) + [""] * (
            len(intestazioni) - len(valori)
        )
        dati.append(
            {
                intestazioni[indice]: _normalizza_valore(valore)
                for indice, valore in enumerate(
                    valori_estesi[: len(intestazioni)]
                )
            }
        )
    return dati


def leggi_file(nome_file: str, contenuto: bytes) -> list[dict[str, Any]]:
    if nome_file.lower().endswith(".xlsx"):
        return _leggi_xlsx(contenuto)
    if nome_file.lower().endswith(".csv"):
        return _leggi_csv(contenuto)
    raise ValidationError("Formato del file non supportato.")


def _parse_data(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    testo = str(value or "").strip()
    for formato in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(testo, formato).date()
        except ValueError:
            continue
    raise ValidationError(
        "Data non valida. Usare YYYY-MM-DD oppure DD/MM/YYYY."
    )


def _parse_intero(value: Any, campo: str) -> int:
    try:
        numero = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"{campo} deve essere un numero intero."
        ) from exc
    if numero <= 0:
        raise ValidationError(
            f"{campo} deve essere maggiore di zero."
        )
    return numero


def _parse_decimal(value: Any, campo: str) -> Decimal:
    testo = str(value or "").strip().replace("€", "").replace(" ", "")
    if "," in testo and "." in testo:
        if testo.rfind(",") > testo.rfind("."):
            testo = testo.replace(".", "").replace(",", ".")
        else:
            testo = testo.replace(",", "")
    else:
        testo = testo.replace(",", ".")

    try:
        numero = Decimal(testo)
    except InvalidOperation as exc:
        raise ValidationError(
            f"{campo} deve essere un importo numerico."
        ) from exc
    if numero <= 0:
        raise ValidationError(
            f"{campo} deve essere maggiore di zero."
        )
    return numero.quantize(Decimal("0.01"))


def _assegnazione_valida(
    *,
    email: str,
    codice_commessa: str,
    nome_fase: str,
    giorno: date,
) -> Assegnazione:
    try:
        consulente = User.objects.get(
            email__iexact=email,
            ruolo=User.Ruolo.CONSULENTE,
            is_active=True,
        )
    except User.DoesNotExist as exc:
        raise ValidationError(
            "Consulente non trovato, non attivo o non classificato "
            "come CONSULENTE."
        ) from exc

    try:
        commessa = Commessa.objects.get(
            codice__iexact=codice_commessa
        )
    except Commessa.DoesNotExist as exc:
        raise ValidationError("Commessa non trovata.") from exc

    nome_fase = nome_fase.strip()
    if not nome_fase:
        raise ValidationError(
            "La fase è obbligatoria per l'importazione."
        )

    try:
        fase = FaseCommessa.objects.get(
            commessa=commessa,
            nome__iexact=nome_fase,
        )
    except FaseCommessa.DoesNotExist as exc:
        raise ValidationError(
            f"Fase '{nome_fase}' non trovata nella commessa {commessa.codice}."
        ) from exc

    assegnazioni = Assegnazione.objects.filter(
        consulente=consulente,
        commessa=commessa,
        fase=fase,
        stato=Assegnazione.Stato.ATTIVA,
        data_inizio__lte=giorno,
    ).filter(
        models.Q(data_fine__isnull=True)
        | models.Q(data_fine__gte=giorno)
    )

    assegnazione = assegnazioni.first()
    if assegnazione is None:
        raise ValidationError(
            "Non esiste un'assegnazione attiva valida per la fase "
            "alla data indicata."
        )
    return assegnazione


# Import locale per evitare di confondere la Q di Django con altri simboli.
from django.db import models


def _valida_riga_ore(
    numero_riga: int,
    riga: dict[str, Any],
) -> RigaAnteprima:
    email = str(riga.get("consulente_email", "")).strip().lower()
    codice = str(riga.get("codice_commessa", "")).strip()
    fase = str(riga.get("fase", "")).strip()
    giorno = _parse_data(riga.get("data"))
    tipo = str(riga.get("tipo_attivita", "")).strip().upper()
    ore = _parse_intero(riga.get("ore"), "Ore")
    nota = str(riga.get("nota", "") or "").strip()

    if tipo not in {
        TariffaAssegnazione.TipoAttivita.FORMAZIONE,
        TariffaAssegnazione.TipoAttivita.CONSULENZA,
    }:
        raise ValidationError(
            "Tipo attività non valido: usare FORMAZIONE o CONSULENZA."
        )

    if periodo_chiuso(giorno):
        raise ValidationError(
            "Il mese della riga è chiuso e non può essere importato."
        )

    assegnazione = _assegnazione_valida(
        email=email,
        codice_commessa=codice,
        nome_fase=fase,
        giorno=giorno,
    )

    return RigaAnteprima(
        numero_riga=numero_riga,
        dati={
            "assegnazione_id": str(assegnazione.id),
            "consulente_email": email,
            "codice_commessa": assegnazione.commessa.codice,
            "fase": assegnazione.fase.nome,
            "data": giorno.isoformat(),
            "tipo_attivita": tipo,
            "ore": ore,
            "nota": nota,
        },
    )


def _valida_riga_spesa(
    numero_riga: int,
    riga: dict[str, Any],
) -> RigaAnteprima:
    email = str(riga.get("consulente_email", "")).strip().lower()
    codice = str(riga.get("codice_commessa", "")).strip()
    fase = str(riga.get("fase", "")).strip()
    giorno = _parse_data(riga.get("data"))
    categoria = str(riga.get("categoria", "")).strip().upper()
    importo = _parse_decimal(riga.get("importo"), "Importo")
    nota = str(riga.get("nota", "") or "").strip()

    if categoria not in {
        SpesaTrasferta.Categoria.VIAGGIO,
        SpesaTrasferta.Categoria.VITTO,
        SpesaTrasferta.Categoria.ALLOGGIO,
        SpesaTrasferta.Categoria.ALTRO,
    }:
        raise ValidationError(
            "Categoria non valida: usare VIAGGIO, VITTO, ALLOGGIO o ALTRO."
        )

    if periodo_chiuso(giorno):
        raise ValidationError(
            "Il mese della riga è chiuso e non può essere importato."
        )

    assegnazione = _assegnazione_valida(
        email=email,
        codice_commessa=codice,
        nome_fase=fase,
        giorno=giorno,
    )

    return RigaAnteprima(
        numero_riga=numero_riga,
        dati={
            "assegnazione_id": str(assegnazione.id),
            "consulente_email": email,
            "codice_commessa": assegnazione.commessa.codice,
            "fase": assegnazione.fase.nome,
            "data": giorno.isoformat(),
            "categoria": categoria,
            "importo": str(importo),
            "nota": nota,
        },
    )


def prepara_importazione(
    *,
    attore: User,
    tipo_importazione: str,
    nome_file: str,
    contenuto: bytes,
) -> AnteprimaImportazione:
    if tipo_importazione not in COLONNE_OBBLIGATORIE:
        raise ValidationError("Tipo di importazione non valido.")

    if len(contenuto) > IMPORT_MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError(
            f"Il file supera la dimensione massima di "
            f"{IMPORT_MAX_UPLOAD_SIZE_MB} MB."
        )

    validate_import_content(nome_file, contenuto)

    file_hash = hashlib.sha256(contenuto).hexdigest()
    if Importazione.objects.filter(
        file_hash=file_hash,
        stato=Importazione.Stato.COMPLETATA,
    ).exists():
        raise ValidationError(
            "Questo file risulta già importato con successo."
        )

    importazione = Importazione.objects.create(
        avviata_da=attore,
        nome_file=nome_file,
        file_hash=file_hash,
        stato=Importazione.Stato.VALIDAZIONE,
    )

    try:
        righe = leggi_file(nome_file, contenuto)
    except Exception:
        importazione.stato = Importazione.Stato.ERRORE
        importazione.save(update_fields=["stato", "updated_at"])
        raise

    importazione.righe_totali = len(righe)

    if not righe:
        errore = ErroreImportazione.objects.create(
            importazione=importazione,
            numero_riga=1,
            campo="file",
            codice_errore="FILE_VUOTO",
            messaggio="Il file non contiene righe dati.",
            dati_riga={},
        )
        importazione.righe_errore = 1
        importazione.stato = Importazione.Stato.ERRORE
        importazione.save()
        return AnteprimaImportazione(
            importazione=importazione,
            tipo_importazione=tipo_importazione,
            righe_valide=[],
            errori=[errore],
        )

    headers = set(righe[0].keys())
    mancanti = sorted(COLONNE_OBBLIGATORIE[tipo_importazione] - headers)
    if mancanti:
        errore = ErroreImportazione.objects.create(
            importazione=importazione,
            numero_riga=1,
            campo="intestazioni",
            codice_errore="COLONNE_MANCANTI",
            messaggio=(
                "Mancano le colonne obbligatorie: "
                + ", ".join(mancanti)
            ),
            dati_riga={"intestazioni_trovate": sorted(headers)},
        )
        importazione.righe_errore = 1
        importazione.stato = Importazione.Stato.ERRORE
        importazione.save()
        return AnteprimaImportazione(
            importazione=importazione,
            tipo_importazione=tipo_importazione,
            righe_valide=[],
            errori=[errore],
        )

    valide = []
    errori = []

    for indice, riga in enumerate(righe, start=2):
        try:
            if tipo_importazione == "ORE":
                valida = _valida_riga_ore(indice, riga)
            else:
                valida = _valida_riga_spesa(indice, riga)
        except ValidationError as exc:
            messaggio = "; ".join(exc.messages)
            errore = ErroreImportazione.objects.create(
                importazione=importazione,
                numero_riga=indice,
                campo="",
                codice_errore="VALIDAZIONE_RIGA",
                messaggio=messaggio,
                dati_riga={
                    chiave: (
                        valore.isoformat()
                        if isinstance(valore, (date, datetime))
                        else str(valore)
                    )
                    for chiave, valore in riga.items()
                },
            )
            errori.append(errore)
        else:
            valide.append(valida)

    importazione.righe_valide = len(valide)
    importazione.righe_errore = len(errori)
    importazione.stato = (
        Importazione.Stato.PRONTA
        if valide and not errori
        else Importazione.Stato.ERRORE
    )
    importazione.save()

    return AnteprimaImportazione(
        importazione=importazione,
        tipo_importazione=tipo_importazione,
        righe_valide=valide,
        errori=errori,
    )


def serializza_anteprima(
    anteprima: AnteprimaImportazione,
) -> dict[str, Any]:
    return {
        "tipo_importazione": anteprima.tipo_importazione,
        "righe": [
            {
                "numero_riga": riga.numero_riga,
                "dati": riga.dati,
            }
            for riga in anteprima.righe_valide
        ],
    }


def conferma_importazione(
    *,
    attore: User,
    importazione: Importazione,
    dati_sessione: dict[str, Any],
) -> Importazione:
    if importazione.stato != Importazione.Stato.PRONTA:
        raise ValidationError(
            "L'importazione non è pronta o contiene errori."
        )

    tipo = dati_sessione.get("tipo_importazione")
    righe = dati_sessione.get("righe", [])

    if tipo not in {"ORE", "SPESE"} or not righe:
        raise ValidationError(
            "I dati temporanei dell'importazione non sono disponibili."
        )

    try:
        with transaction.atomic():
            for elemento in righe:
                numero_riga = elemento["numero_riga"]
                dati = elemento["dati"]
                try:
                    if tipo == "ORE":
                        inserisci_ore(
                            attore=attore,
                            assegnazione_id=dati["assegnazione_id"],
                            giorno=date.fromisoformat(dati["data"]),
                            tipo_attivita=dati["tipo_attivita"],
                            ore=int(dati["ore"]),
                            nota=dati.get("nota", ""),
                            motivazione="Import amministrativo consuntivi.",
                        )
                    else:
                        inserisci_spesa(
                            attore=attore,
                            assegnazione_id=dati["assegnazione_id"],
                            giorno=date.fromisoformat(dati["data"]),
                            categoria=dati["categoria"],
                            importo=Decimal(dati["importo"]),
                            nota=dati.get("nota", ""),
                        )
                except Exception as exc:
                    raise ErroreCommitImportazione(
                        numero_riga,
                        str(exc),
                    ) from exc

            importazione.stato = Importazione.Stato.COMPLETATA
            importazione.completed_at = timezone.now()
            importazione.save(
                update_fields=[
                    "stato",
                    "completed_at",
                    "updated_at",
                ]
            )
    except ErroreCommitImportazione as exc:
        importazione.refresh_from_db()
        importazione.stato = Importazione.Stato.ERRORE
        importazione.righe_errore = max(
            importazione.righe_errore,
            1,
        )
        importazione.save()
        ErroreImportazione.objects.create(
            importazione=importazione,
            numero_riga=exc.numero_riga,
            campo="",
            codice_errore="ERRORE_COMMIT",
            messaggio=exc.messaggio,
            dati_riga={},
        )
        raise ValidationError(
            "L'importazione è stata annullata: "
            f"errore alla riga {exc.numero_riga}: {exc.messaggio}"
        ) from exc

    return importazione


def crea_template_xlsx(tipo_importazione: str) -> bytes:
    if tipo_importazione not in COLONNE_TEMPLATE:
        raise ValidationError("Tipo di template non valido.")

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Importazione"

    colonne = COLONNE_TEMPLATE[tipo_importazione]
    worksheet.append(colonne)

    if tipo_importazione == "ORE":
        worksheet.append(
            [
                "consulente@example.com",
                "COMM-001",
                "Analisi",
                "2026-07-15",
                "CONSULENZA",
                8,
                "Analisi e affiancamento",
            ]
        )
    else:
        worksheet.append(
            [
                "consulente@example.com",
                "COMM-001",
                "Analisi",
                "2026-07-15",
                "VIAGGIO",
                35.50,
                "Pedaggio autostradale",
            ]
        )

    for column_cells in worksheet.columns:
        max_length = max(
            len(str(cell.value or "")) for cell in column_cells
        )
        worksheet.column_dimensions[
            column_cells[0].column_letter
        ].width = min(max_length + 3, 45)

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
