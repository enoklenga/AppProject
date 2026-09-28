from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.projects.models import Commessa

from .forms import FaseForm
from .models import FaseCommessa
from .permissions import can_edit_fase, can_manage_fasi
from .selectors import (
    fasi_for_commessa,
    manageable_commesse_for_phases,
    visible_commesse_for_user,
)
from .services import create_fase, delete_fase, update_fase


@login_required
def fase_list(request):
    commessa_id = request.GET.get("commessa")

    commesse_visibili = visible_commesse_for_user(request.user).select_related("cliente")

    fasi = FaseCommessa.objects.none()
    commessa_selezionata = None

    if commessa_id:
        commessa_selezionata = get_object_or_404(commesse_visibili, pk=commessa_id)
        fasi = fasi_for_commessa(user=request.user, commessa=commessa_selezionata)

    puo_gestire = (
        commessa_selezionata is not None
        and can_manage_fasi(request.user, commessa_selezionata)
    )

    return render(
        request,
        "phases/fase_list.html",
        {
            "commesse": commesse_visibili,
            "commessa_selezionata": commessa_selezionata,
            "fasi": fasi,
            "puo_gestire": puo_gestire,
        },
    )


@login_required
def fase_create(request):
    if not manageable_commesse_for_phases(request.user).exists():
        raise PermissionDenied("Non puoi creare fasi operative.")

    commessa_id_bloccata = request.GET.get("commessa")
    commessa_bloccata = None

    if commessa_id_bloccata:
        commessa_bloccata = get_object_or_404(Commessa, pk=commessa_id_bloccata)

    if request.method == "POST":
        form = FaseForm(
            request.POST,
            user=request.user,
            commessa_bloccata=commessa_bloccata,
        )

        if form.is_valid():
            commessa = commessa_bloccata or form.cleaned_data["commessa"]

            try:
                fase = create_fase(
                    user=request.user,
                    commessa=commessa,
                    nome=form.cleaned_data["nome"],
                    descrizione=form.cleaned_data["descrizione"],
                    ordine=form.cleaned_data["ordine"],
                    stato=form.cleaned_data["stato"],
                    data_inizio=form.cleaned_data["data_inizio"],
                    data_fine_prevista=form.cleaned_data["data_fine_prevista"],
                )

            except PermissionDenied as exc:
                form.add_error(None, str(exc))

            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))

            else:
                messages.success(request, "Fase creata correttamente.")

                return redirect(f"{_fase_list_url()}?commessa={fase.commessa_id}")

    else:
        form = FaseForm(user=request.user, commessa_bloccata=commessa_bloccata)

    return render(
        request,
        "phases/fase_form.html",
        {"form": form, "titolo": "Nuova fase", "is_update": False},
    )


@login_required
def fase_update(request, pk):
    fase = get_object_or_404(FaseCommessa.objects.select_related("commessa", "commessa__cliente"), pk=pk)

    if not can_edit_fase(request.user, fase):
        raise PermissionDenied("Non puoi modificare questa fase.")

    if request.method == "POST":
        form = FaseForm(
            request.POST,
            user=request.user,
            commessa_bloccata=fase.commessa,
        )

        if form.is_valid():
            try:
                update_fase(
                    user=request.user,
                    fase=fase,
                    nome=form.cleaned_data["nome"],
                    descrizione=form.cleaned_data["descrizione"],
                    ordine=form.cleaned_data["ordine"],
                    stato=form.cleaned_data["stato"],
                    data_inizio=form.cleaned_data["data_inizio"],
                    data_fine_prevista=form.cleaned_data["data_fine_prevista"],
                )

            except PermissionDenied as exc:
                form.add_error(None, str(exc))

            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))

            else:
                messages.success(request, "Fase aggiornata correttamente.")

                return redirect(f"{_fase_list_url()}?commessa={fase.commessa_id}")

    else:
        form = FaseForm(
            user=request.user,
            commessa_bloccata=fase.commessa,
            initial={
                "nome": fase.nome,
                "descrizione": fase.descrizione,
                "ordine": fase.ordine,
                "stato": fase.stato,
                "data_inizio": fase.data_inizio,
                "data_fine_prevista": fase.data_fine_prevista,
            },
        )

    return render(
        request,
        "phases/fase_form.html",
        {"form": form, "titolo": f"Modifica fase — {fase.nome}", "is_update": True, "fase": fase},
    )


@login_required
def fase_delete(request, pk):
    fase = get_object_or_404(
        FaseCommessa.objects.select_related("commessa"),
        pk=pk,
    )

    # Il 403 deve essere usato solo quando l'utente non ha i permessi
    # gestionali sulla commessa. Una fase tecnica di sistema, invece,
    # non è eliminabile per regola di dominio: è quindi un errore
    # business gestito, non un errore di autorizzazione.
    if not can_manage_fasi(request.user, fase.commessa):
        raise PermissionDenied("Non puoi eliminare questa fase.")

    if fase.sistema:
        messages.error(
            request,
            "La fase Generale è la fase predefinita della commessa e non può essere eliminata.",
        )
        return redirect(
            f"{_fase_list_url()}?commessa={fase.commessa_id}"
        )

    if request.method == "POST":
        commessa_id = fase.commessa_id

        try:
            delete_fase(user=request.user, fase=fase)

        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))

            return redirect(f"{_fase_list_url()}?commessa={commessa_id}")

        messages.success(request, "Fase eliminata.")

        return redirect(f"{_fase_list_url()}?commessa={commessa_id}")

    return render(
        request,
        "phases/fase_confirm_delete.html",
        {"fase": fase},
    )


def _fase_list_url():
    return reverse("phases:fase-list")
