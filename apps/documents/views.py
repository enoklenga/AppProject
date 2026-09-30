from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.projects.models import Assegnazione, Commessa
from apps.phases.models import FaseCommessa

from .forms import DocumentoUploadForm
from .models import DocumentoCommessa
from .permissions import can_delete_document, can_view_documents
from .selectors import (
    manageable_projects_for_upload,
    visible_documents_for_user,
    visible_projects_for_documents,
)
from .services import delete_document, upload_document


def _uuid_or_none(valore):
    """Parametri GET non validi vengono ignorati invece di generare un errore 500."""
    import uuid

    try:
        return str(uuid.UUID(str(valore))) if valore else None
    except (TypeError, ValueError):
        return None


@login_required
def document_list(request):
    queryset = visible_documents_for_user(request.user)

    commessa_id = _uuid_or_none(request.GET.get("commessa"))
    fase_id = _uuid_or_none(request.GET.get("fase"))
    categoria = request.GET.get("categoria")

    if commessa_id:
        queryset = queryset.filter(commessa_id=commessa_id)

    if fase_id:
        queryset = queryset.filter(fase_id=fase_id)

    if categoria:
        queryset = queryset.filter(categoria=categoria)

    if commessa_id:
        fasi = FaseCommessa.objects.filter(commessa_id=commessa_id)
        from apps.accounts.access import can_view_all_documents
        commessa_filtro = Commessa.objects.filter(pk=commessa_id).first()
        if (
            not request.user.puo_gestire_commessa(commessa_filtro)
            and not can_view_all_documents(request.user)
        ):
            fasi = fasi.filter(
                assegnazioni__consulente=request.user,
                assegnazioni__stato=Assegnazione.Stato.ATTIVA,
            ).distinct()
        fasi = fasi.order_by("ordine", "nome")
    else:
        fasi = FaseCommessa.objects.none()

    commesse = (
        visible_projects_for_documents(request.user)
        .select_related("cliente")
        .order_by("codice")
    )

    # Le commesse su cui poter caricare un nuovo documento possono essere
    # più di quelle con documenti già presenti: le serve comunque per il
    # filtro e per decidere se mostrare il pulsante "Carica documento".
    puo_caricare = manageable_projects_for_upload(request.user).exists()

    # Il pulsante "Elimina" deve comparire solo a chi può davvero eliminare
    # (stessa regola applicata dalla vista document_delete): evita link che
    # portano a un 403 per Commerciale, Direzione e documenti privati.
    documenti = list(
        queryset.select_related("commessa", "commessa__cliente", "fase", "caricato_da")
    )
    for documento in documenti:
        documento.puo_eliminare = can_delete_document(request.user, documento)

    context = {
        "documenti": documenti,
        "commesse": commesse,
        "categorie": DocumentoCommessa.Categoria.choices,
        "commessa_selezionata": commessa_id or "",
        "fase_selezionata": fase_id or "",
        "fasi": fasi,
        "categoria_selezionata": categoria or "",
        "totale": len(documenti),
        "puo_caricare": puo_caricare,
    }

    return render(request, "documents/document_list.html", context)

@login_required
def document_phases(request):
    commessa_id = request.GET.get("commessa")

    if not commessa_id:
        return JsonResponse({"results": []})

    commessa = (
        manageable_projects_for_upload(request.user)
        .filter(pk=commessa_id)
        .first()
    )

    if commessa is None:
        raise PermissionDenied(
            "Non puoi caricare documenti su questa commessa."
        )

    fasi = (
        FaseCommessa.objects
        .filter(commessa=commessa)
        .order_by("ordine", "nome")
    )

    return JsonResponse(
        {
            "results": [
                {
                    "id": str(fase.pk),
                    "label": fase.nome,
                }
                for fase in fasi
            ]
        }
    )

@login_required
def document_upload(request):
    if not manageable_projects_for_upload(request.user).exists():
        raise PermissionDenied("Non hai commesse su cui caricare documenti.")

    commessa_id_bloccata = request.GET.get("commessa")
    commessa_bloccata = None

    if commessa_id_bloccata:
        commessa_bloccata = get_object_or_404(
            manageable_projects_for_upload(request.user),
            pk=commessa_id_bloccata,
        )

    if request.method == "POST":
        form = DocumentoUploadForm(
            request.POST,
            request.FILES,
            user=request.user,
            commessa_bloccata=commessa_bloccata,
        )

        if form.is_valid():
            commessa = (
                commessa_bloccata
                or form.cleaned_data["commessa"]
            )

            try:
                upload_document(
                    user=request.user,
                    commessa=commessa,
                    fase=form.cleaned_data.get("fase"),
                    file=form.cleaned_data["file"],
                    categoria=form.cleaned_data["categoria"],
                    descrizione=form.cleaned_data["descrizione"],
                    privato=form.cleaned_data.get("privato", False),
                )

            except (PermissionDenied, ValidationError) as exc:
                messages.error(request, str(exc))

            else:
                messages.success(
                    request,
                    "Documento caricato correttamente.",
                )

                return redirect("documents:document-list")

    else:
        form = DocumentoUploadForm(
            user=request.user,
            commessa_bloccata=commessa_bloccata,
        )

    return render(
        request,
        "documents/document_upload.html",
        {"form": form, "commessa_bloccata": commessa_bloccata},
    )


@login_required
def document_download(request, pk):
    documento = get_object_or_404(
        DocumentoCommessa.objects.select_related("commessa", "fase"),
        pk=pk,
    )

    if not can_view_documents(request.user, documento.commessa, documento.fase, documento.privato):
        raise PermissionDenied(
            "Non puoi scaricare questo documento."
        )

    if not documento.file.storage.exists(documento.file.name):
        raise Http404("Il file non è più disponibile.")

    return FileResponse(
        documento.file.open("rb"),
        as_attachment=True,
        filename=documento.nome_originale,
    )


@login_required
def document_delete(request, pk):
    documento = get_object_or_404(DocumentoCommessa, pk=pk)

    if not can_delete_document(request.user, documento):
        raise PermissionDenied(
            "Non puoi eliminare questo documento."
        )

    if request.method == "POST":
        delete_document(user=request.user, documento=documento)

        messages.success(
            request,
            "Documento eliminato.",
        )

        return redirect("documents:document-list")

    return render(
        request,
        "documents/document_confirm_delete.html",
        {"documento": documento},
    )
