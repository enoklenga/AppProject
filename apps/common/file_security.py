"""Validazione leggera del contenuto dei file caricati."""

from __future__ import annotations

import zipfile
from pathlib import PurePath

from django.core.exceptions import ValidationError


ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
PDF_SIGNATURE = b"%PDF-"

ZIP_OFFICE_PREFIX = {
    "docx": "word/",
    "xlsx": "xl/",
    "pptx": "ppt/",
}

ODF_MIME = {
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "odp": "application/vnd.oasis.opendocument.presentation",
}


def basename_for_upload(filename: str) -> str:
    # PurePath su POSIX non considera '\\' un separatore: normalizziamo prima.
    normalized = str(filename or "").replace("\\", "/")
    return PurePath(normalized).name


def _peek(uploaded_file, size: int = 8192) -> bytes:
    position = None
    try:
        position = uploaded_file.tell()
    except (AttributeError, OSError):
        pass

    try:
        uploaded_file.seek(0)
        return uploaded_file.read(size)
    finally:
        try:
            uploaded_file.seek(0 if position is None else position)
        except (AttributeError, OSError):
            pass


def _zip_names(uploaded_file) -> tuple[set[str], bytes | None]:
    position = None
    try:
        position = uploaded_file.tell()
    except (AttributeError, OSError):
        pass

    try:
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as archive:
            names = set(archive.namelist())
            mimetype = None
            if "mimetype" in names:
                try:
                    mimetype = archive.read("mimetype")[:200]
                except (KeyError, RuntimeError, OSError):
                    mimetype = None
            return names, mimetype
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise ValidationError(
            "Il contenuto del file non corrisponde a un archivio valido."
        ) from exc
    finally:
        try:
            uploaded_file.seek(0 if position is None else position)
        except (AttributeError, OSError):
            pass


def validate_uploaded_document_content(uploaded_file, extension: str) -> None:
    extension = (extension or "").lower().lstrip(".")
    prefix = _peek(uploaded_file)

    if extension == "pdf":
        valid = prefix.startswith(PDF_SIGNATURE)
    elif extension in {"jpg", "jpeg"}:
        valid = prefix.startswith(JPEG_SIGNATURE)
    elif extension == "png":
        valid = prefix.startswith(PNG_SIGNATURE)
    elif extension in {"doc", "xls", "ppt"}:
        valid = prefix.startswith(OLE_SIGNATURE)
    elif extension in {"txt", "csv"}:
        valid = b"\x00" not in prefix
    elif extension == "zip":
        valid = prefix.startswith(ZIP_SIGNATURES)
        if valid:
            _zip_names(uploaded_file)
    elif extension in ZIP_OFFICE_PREFIX:
        if not prefix.startswith(ZIP_SIGNATURES):
            valid = False
        else:
            names, _ = _zip_names(uploaded_file)
            required_prefix = ZIP_OFFICE_PREFIX[extension]
            valid = (
                "[Content_Types].xml" in names
                and any(name.startswith(required_prefix) for name in names)
            )
    elif extension in ODF_MIME:
        if not prefix.startswith(ZIP_SIGNATURES):
            valid = False
        else:
            _, mimetype = _zip_names(uploaded_file)
            valid = (
                mimetype is not None
                and mimetype.decode("ascii", errors="ignore").strip()
                == ODF_MIME[extension]
            )
    else:
        valid = False

    if not valid:
        raise ValidationError(
            "Il contenuto del file non corrisponde al formato indicato "
            f"dall'estensione .{extension}."
        )


def validate_import_content(filename: str, content: bytes) -> None:
    name = basename_for_upload(filename).lower()
    if name.endswith(".xlsx"):
        if not content.startswith(ZIP_SIGNATURES):
            raise ValidationError(
                "Il contenuto del file non corrisponde a un file XLSX valido."
            )
        # openpyxl farà la validazione strutturale completa; qui blocchiamo
        # subito file binari rinominati con estensione .xlsx.
        return

    if name.endswith(".csv"):
        if b"\x00" in content[:8192]:
            raise ValidationError(
                "Il contenuto del file non corrisponde a un CSV testuale valido."
            )
        return

    raise ValidationError("Il file deve essere in formato .xlsx oppure .csv.")
