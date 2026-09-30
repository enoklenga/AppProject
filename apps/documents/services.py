from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.text import get_valid_filename

from apps.common.file_security import (
    basename_for_upload,
    validate_uploaded_document_content,
)

from apps.notifications.services import notify_documento_caricato, notify_documento_eliminato

from .models import DocumentoCommessa
from .permissions import can_delete_document, can_upload_document

# Limite di dimensione file, configurabile da .env (default 10 MB).
DIMENSIONE_MASSIMA_MB = getattr(settings, "DOCUMENTS_MAX_UPLOAD_SIZE_MB", 10)
DIMENSIONE_MASSIMA_BYTE = DIMENSIONE_MASSIMA_MB * 1024 * 1024

# Tipi di file più comuni per contratti/obiettivi/materiale di commessa.
# Volutamente non includiamo eseguibili o script.
ESTENSIONI_CONSENTITE = {
    "pdf",
    "doc", "docx",
    "xls", "xlsx",
    "ppt", "pptx",
    "odt", "ods", "odp",
    "txt", "csv",
    "jpg", "jpeg", "png",
    "zip",
}


def _valida_file(file) -> None:
    if file.size > DIMENSIONE_MASSIMA_BYTE:
        raise ValidationError(
            f"Il file supera la dimensione massima consentita di "
            f"{DIMENSIONE_MASSIMA_MB} MB."
        )

    estensione = (
        file.name.rsplit(".", 1)[-1].lower()
        if "." in file.name
        else ""
    )

    if estensione not in ESTENSIONI_CONSENTITE:
        raise ValidationError(
            f"Formato file non consentito (.{estensione}). "
            f"Formati ammessi: {', '.join(sorted(ESTENSIONI_CONSENTITE))}."
        )

    validate_uploaded_document_content(file, estensione)


@transaction.atomic
def upload_document(
    *,
    user,
    commessa,
    file,
    categoria,
    fase=None,
    descrizione="",
    privato=False,
) -> DocumentoCommessa:
    if not can_upload_document(user, commessa, fase):
        raise PermissionDenied(
            "Non puoi caricare documenti su questa commessa."
        )

    _valida_file(file)

    # Normalizza il nome usato sul filesystem e conserva come nome originale
    # solo il basename, evitando path o caratteri non sicuri inviati dal client.
    nome_originale = basename_for_upload(file.name)[:255] or "documento"
    nome_storage = get_valid_filename(nome_originale) or "documento"
    if len(nome_storage) > 180:
        if "." in nome_storage:
            stem, ext = nome_storage.rsplit(".", 1)
            nome_storage = f"{stem[:160]}.{ext[:15]}"
        else:
            nome_storage = nome_storage[:180]
    file.name = nome_storage

    if fase is not None and fase.commessa_id != commessa.id:
        raise ValidationError("La fase non appartiene alla commessa selezionata.")

    # Rete di sicurezza: solo chi gestisce la commessa (Admin, Amministrazione,
    # Resp. BU) può marcare un documento come privato.
    privato = bool(privato) and user.puo_gestire_commessa(commessa)

    documento = DocumentoCommessa.objects.create(
        commessa=commessa,
        fase=fase,
        file=file,
        nome_originale=nome_originale,
        categoria=categoria,
        descrizione=descrizione,
        dimensione_byte=file.size,
        caricato_da=user,
        privato=privato,
    )

    notify_documento_caricato(
        documento=documento,
        actor=user,
    )

    return documento


@transaction.atomic
def delete_document(*, user, documento: DocumentoCommessa) -> None:
    if not can_delete_document(user, documento):
        raise PermissionDenied(
            "Non puoi eliminare questo documento."
        )

    notify_documento_eliminato(
        documento=documento,
        actor=user,
    )

    # Rimuove anche il file fisico dal disco, non solo il record.
    documento.file.delete(save=False)
    documento.delete()
