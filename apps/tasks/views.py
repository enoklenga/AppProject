from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.projects.models import Commessa
from apps.phases.models import FaseCommessa
from apps.accounts.access import can_view_tasks_portfolio

from .forms import (
    TaskCommentForm,
    TaskForm,
    TaskStatusForm,
)
from .models import Task
from .permissions import (
    can_comment_task,
    can_create_task,
    can_delete_task,
    can_edit_task,
    can_update_task_status,
    can_view_task,
)
from .selectors import (
    assignable_users_for_phase,
    assignable_users_for_project,
    due_soon_tasks,
    manageable_phases_for_user,
    manageable_projects_for_user,
    my_tasks,
    overdue_tasks,
    task_summary,
    task_with_comments,
    visible_tasks_for_user,
)
from .services import (
    add_task_comment,
    create_task,
    delete_task,
    update_task,
    update_task_status,
)


def _add_validation_errors(form, exc):
    """
    Trasforma una ValidationError del service
    in errore visibile nel form.
    """

    for message in exc.messages:
        form.add_error(
            None,
            message,
        )


def _attivita_url(**params):
    base = reverse(
        "tasks:task-list"
    )

    params = {
        key: value
        for key, value in params.items()
        if value not in (
            None,
            "",
        )
    }

    if not params:
        return base

    return (
        f"{base}?"
        f"{urlencode(params)}"
    )


def _mie_attivita_url(**params):
    base = reverse(
        "tasks:my-task-list"
    )

    params = {
        key: value
        for key, value in params.items()
        if value not in (
            None,
            "",
        )
    }

    if not params:
        return base

    return (
        f"{base}?"
        f"{urlencode(params)}"
    )


def _user_can_manage_tasks(user):
    """
    True se l'utente può accedere alla sezione
    gestionale Attività.

    Admin:
        sempre.

    Membro del Teamwork:
        se ha almeno una commessa attiva assegnata.
    """

    if user.is_admin_lef:
        return True

    return (
        manageable_projects_for_user(
            user
        )
        .exists()
    )


def _user_can_view_tasks(user):
    return bool(
        _user_can_manage_tasks(user)
        or can_view_tasks_portfolio(user)
    )


# =========================================================
# ATTIVITÀ — ADMIN / PM
# =========================================================


@login_required
def task_list(request):
    """
    Vista gestionale Task.

    Disponibile ai membri del Teamwork.
    """

    if not _user_can_view_tasks(
        request.user
    ):
        raise PermissionDenied(
            "Non hai accesso alla gestione delle attività."
        )

    queryset = visible_tasks_for_user(
        request.user
    )

    # -----------------------------------------------------
    # FILTRI
    # -----------------------------------------------------

    commessa_id = request.GET.get("commessa")
    fase_id = request.GET.get("fase")

    assegnato_a_id = request.GET.get(
        "assegnato_a"
    )

    stato = request.GET.get(
        "stato"
    )

    priorita = request.GET.get(
        "priorita"
    )

    ricerca = (
        request.GET.get(
            "q",
            "",
        )
        .strip()
    )

    if commessa_id:
        queryset = queryset.filter(commessa_id=commessa_id)
    if fase_id:
        queryset = queryset.filter(fase_id=fase_id)

    if assegnato_a_id:
        queryset = queryset.filter(
            assegnato_a_id=assegnato_a_id,
        )

    if stato:
        queryset = queryset.filter(
            stato=stato,
        )

    if priorita:
        queryset = queryset.filter(
            priorita=priorita,
        )

    if ricerca:
        queryset = queryset.filter(
            titolo__icontains=ricerca,
        )

    # -----------------------------------------------------
    # VISTA (lista tabellare o bacheca a colonne)
    # -----------------------------------------------------

    vista = request.GET.get(
        "vista",
        "lista",
    )

    if vista not in {"lista", "board"}:
        vista = "lista"

    colonne_board = []

    if vista == "board":
        for valore, etichetta in Task.Stato.choices:
            colonne_board.append(
                {
                    "valore": valore,
                    "etichetta": etichetta,
                    "task": [
                        task
                        for task in queryset
                        if task.stato == valore
                    ],
                }
            )

    querystring_corrente = request.GET.copy()
    querystring_corrente.pop("vista", None)
    querystring_base = querystring_corrente.urlencode()

    # -----------------------------------------------------
    # COMMESSE VISIBILI
    # -----------------------------------------------------

    if can_view_tasks_portfolio(request.user):
        commesse = Commessa.objects.select_related("cliente").order_by("codice")
    else:
        commesse = manageable_projects_for_user(request.user)

    # -----------------------------------------------------
    # ASSEGNATARI VISIBILI
    # -----------------------------------------------------

    utenti_ids = (
        visible_tasks_for_user(
            request.user
        )
        .values_list(
            "assegnato_a_id",
            flat=True,
        )
        .distinct()
    )

    from django.contrib.auth import get_user_model

    User = get_user_model()

    assegnatari = (
        User.objects
        .filter(
            pk__in=utenti_ids,
        )
        .order_by(
            "last_name",
            "first_name",
            "email",
        )
    )

    fasi = FaseCommessa.objects.filter(
        pk__in=visible_tasks_for_user(request.user).values_list("fase_id", flat=True)
    ).select_related("commessa").distinct().order_by("commessa__codice", "ordine", "nome")

    # -----------------------------------------------------
    # KPI
    # -----------------------------------------------------

    base_queryset = visible_tasks_for_user(
        request.user
    )

    totale = base_queryset.count()

    da_fare = base_queryset.filter(
        stato=Task.Stato.DA_FARE,
    ).count()

    in_corso = base_queryset.filter(
        stato=Task.Stato.IN_CORSO,
    ).count()

    completate = base_queryset.filter(
        stato=Task.Stato.COMPLETATA,
    ).count()

    scadute = sum(
        1
        for task in base_queryset.exclude(
            stato=Task.Stato.COMPLETATA,
        )
        if task.scaduta
    )

    context = {
        "tasks": queryset,
        "commesse": commesse,
        "fasi": fasi,
        "assegnatari": assegnatari,

        "stati": Task.Stato.choices,
        "priorita": Task.Priorita.choices,

        "commessa_selezionata": (commessa_id or ""),
        "fase_selezionata": (fase_id or ""),
        "assegnatario_selezionato": (
            assegnato_a_id
            or ""
        ),
        "stato_selezionato": (
            stato
            or ""
        ),
        "priorita_selezionata": (
            priorita
            or ""
        ),
        "ricerca": ricerca,

        "totale": totale,
        "da_fare": da_fare,
        "in_corso": in_corso,
        "completate": completate,
        "scadute": scadute,

        "vista": vista,
        "colonne_board": colonne_board,
        "lista_url": (
            f"?{querystring_base}&vista=lista"
            if querystring_base
            else "?vista=lista"
        ),
        "board_url": (
            f"?{querystring_base}&vista=board"
            if querystring_base
            else "?vista=board"
        ),
        "puo_gestire_task": _user_can_manage_tasks(request.user),
    }

    return render(
        request,
        "tasks/task_list.html",
        context,
    )


# =========================================================
# LE MIE ATTIVITÀ
# =========================================================


@login_required
def my_task_list(request):
    """
    Attività assegnate direttamente all'utente.
    """

    include_completed = (
        request.GET.get(
            "completate"
        )
        == "1"
    )

    queryset = my_tasks(
        user=request.user,
        include_completed=include_completed,
    )

    stato = request.GET.get(
        "stato"
    )

    priorita = request.GET.get(
        "priorita"
    )

    commessa_id = request.GET.get(
        "commessa"
    )

    if stato:
        queryset = queryset.filter(
            stato=stato,
        )

    if priorita:
        queryset = queryset.filter(
            priorita=priorita,
        )

    if commessa_id:
        queryset = queryset.filter(
            commessa_id=commessa_id,
        )

    summary = task_summary(
        user=request.user
    )

    scadute_queryset = overdue_tasks(
        user=request.user
    )

    in_scadenza_queryset = due_soon_tasks(
        user=request.user,
        giorni=7,
    )

    commesse = (
        Commessa.objects
        .filter(
            tasks__assegnato_a=request.user,
        )
        .select_related(
            "cliente"
        )
        .distinct()
        .order_by(
            "codice"
        )
    )

    context = {
        "tasks": queryset,

        "summary": summary,

        "numero_scadute": (
            scadute_queryset.count()
        ),
        "numero_in_scadenza": (
            in_scadenza_queryset.count()
        ),

        "commesse": commesse,

        "stati": Task.Stato.choices,
        "priorita": Task.Priorita.choices,

        "stato_selezionato": (
            stato
            or ""
        ),
        "priorita_selezionata": (
            priorita
            or ""
        ),
        "commessa_selezionata": (
            commessa_id
            or ""
        ),

        "include_completed": (
            include_completed
        ),

        "puo_gestire_task": (
            _user_can_manage_tasks(
                request.user
            )
        ),
    }

    return render(
        request,
        "tasks/my_task_list.html",
        context,
    )


# =========================================================
# DETTAGLIO TASK
# =========================================================


@login_required
def task_detail(
    request,
    pk,
):
    task = get_object_or_404(
        task_with_comments(
            user=request.user,
            pk=pk,
        )
    )

    if not can_view_task(
        request.user,
        task,
    ):
        raise PermissionDenied

    context = {
        "task": task,

        "comment_form": (
            TaskCommentForm()
        ),

        "status_form": (
            TaskStatusForm(
                task=task
            )
        ),

        "can_edit": (
            can_edit_task(
                request.user,
                task,
            )
        ),

        "can_update_status": (
            can_update_task_status(
                request.user,
                task,
            )
        ),

        "can_comment": (
            can_comment_task(
                request.user,
                task,
            )
        ),

        "can_delete": (
            can_delete_task(
                request.user,
                task,
            )
        ),

        "puo_gestire_task": (
            _user_can_manage_tasks(
                request.user
            )
        ),
    }

    return render(
        request,
        "tasks/task_detail.html",
        context,
    )


# =========================================================
# CREAZIONE
# =========================================================


@login_required
def task_create(request):
    commessa = None

    commessa_id = request.GET.get(
        "commessa"
    )

    if commessa_id:
        commessa = (
            manageable_projects_for_user(
                request.user
            )
            .filter(
                pk=commessa_id
            )
            .first()
        )

    if not _user_can_manage_tasks(
        request.user
    ):
        raise PermissionDenied(
            "Non puoi creare attività."
        )

    if request.method == "POST":
        form = TaskForm(
            request.POST,
            user=request.user,
        )

        if form.is_valid():
            try:
                task = create_task(
                    user=request.user,
                    commessa=form.cleaned_data["commessa"],
                    fase=form.cleaned_data["fase"],
                    assegnato_a=(
                        form.cleaned_data[
                            "assegnato_a"
                        ]
                    ),
                    titolo=(
                        form.cleaned_data[
                            "titolo"
                        ]
                    ),
                    descrizione=(
                        form.cleaned_data[
                            "descrizione"
                        ]
                    ),
                    priorita=(
                        form.cleaned_data[
                            "priorita"
                        ]
                    ),
                    data_inizio=(
                        form.cleaned_data[
                            "data_inizio"
                        ]
                    ),
                    data_scadenza=(
                        form.cleaned_data[
                            "data_scadenza"
                        ]
                    ),
                )

            except PermissionDenied as exc:
                form.add_error(
                    None,
                    str(exc),
                )

            except ValidationError as exc:
                _add_validation_errors(
                    form,
                    exc,
                )

            else:
                messages.success(
                    request,
                    "Attività creata correttamente.",
                )

                return redirect(
                    "tasks:task-detail",
                    pk=task.pk,
                )

    else:
        form = TaskForm(
            user=request.user,
            commessa=commessa,
        )

    return render(
        request,
        "tasks/task_form.html",
        {
            "form": form,
            "titolo": "Nuova attività",
            "is_update": False,
        },
    )


# =========================================================
# MODIFICA
# =========================================================


@login_required
def task_update(
    request,
    pk,
):
    task = get_object_or_404(
        Task.objects.select_related(
            "commessa",
            "commessa__cliente",
            "fase",
            "fase__commessa",
            "assegnato_a",
            "creato_da",
        ),
        pk=pk,
    )

    if not can_edit_task(
        request.user,
        task,
    ):
        raise PermissionDenied(
            "Non puoi modificare questa attività."
        )

    if request.method == "POST":
        form = TaskForm(
            request.POST,
            user=request.user,
            task=task,
        )

        if form.is_valid():
            try:
                task = update_task(
                    user=request.user,
                    task=task,
                    titolo=(
                        form.cleaned_data[
                            "titolo"
                        ]
                    ),
                    descrizione=(
                        form.cleaned_data[
                            "descrizione"
                        ]
                    ),
                    fase=form.cleaned_data["fase"],
                    assegnato_a=(
                        form.cleaned_data[
                            "assegnato_a"
                        ]
                    ),
                    priorita=(
                        form.cleaned_data[
                            "priorita"
                        ]
                    ),
                    data_inizio=(
                        form.cleaned_data[
                            "data_inizio"
                        ]
                    ),
                    data_scadenza=(
                        form.cleaned_data[
                            "data_scadenza"
                        ]
                    ),
                )

            except PermissionDenied as exc:
                form.add_error(
                    None,
                    str(exc),
                )

            except ValidationError as exc:
                _add_validation_errors(
                    form,
                    exc,
                )

            else:
                messages.success(
                    request,
                    "Attività aggiornata correttamente.",
                )

                return redirect(
                    "tasks:task-detail",
                    pk=task.pk,
                )

    else:
        form = TaskForm(
            user=request.user,
            task=task,
        )

    return render(
        request,
        "tasks/task_form.html",
        {
            "form": form,
            "task": task,
            "titolo": "Modifica attività",
            "is_update": True,
        },
    )


# =========================================================
# CAMBIO STATO
# =========================================================


def _redirect_dopo_cambio_stato(request, task):
    """
    Dopo un cambio di stato, torna alla pagina di provenienza (tipicamente
    la bacheca) se indicata ed è un URL interno sicuro; altrimenti torna
    al dettaglio del task, comportamento di sempre.
    """

    destinazione = request.POST.get("next", "")

    if destinazione and url_has_allowed_host_and_scheme(
        url=destinazione,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(destinazione)

    return redirect(
        "tasks:task-detail",
        pk=task.pk,
    )


@login_required
def task_status_update(
    request,
    pk,
):
    task = get_object_or_404(
        Task.objects.select_related(
            "commessa",
            "assegnato_a",
        ),
        pk=pk,
    )

    if not can_update_task_status(
        request.user,
        task,
    ):
        raise PermissionDenied(
            "Non puoi modificare lo stato "
            "di questa attività."
        )

    if request.method != "POST":
        return redirect(
            "tasks:task-detail",
            pk=task.pk,
        )

    form = TaskStatusForm(
        request.POST,
        task=task,
    )

    if form.is_valid():
        try:
            update_task_status(
                user=request.user,
                task=task,
                stato=(
                    form.cleaned_data[
                        "stato"
                    ]
                ),
            )

        except (
            PermissionDenied,
            ValidationError,
        ) as exc:
            messages.error(
                request,
                str(exc),
            )

        else:
            messages.success(
                request,
                "Stato aggiornato correttamente.",
            )

    else:
        messages.error(
            request,
            "Stato non valido.",
        )

    return _redirect_dopo_cambio_stato(request, task)


# =========================================================
# COMMENTO
# =========================================================


@login_required
def task_comment_create(
    request,
    pk,
):
    task = get_object_or_404(
        Task.objects.select_related(
            "commessa",
            "assegnato_a",
        ),
        pk=pk,
    )

    if not can_comment_task(
        request.user,
        task,
    ):
        raise PermissionDenied(
            "Non puoi commentare questa attività."
        )

    if request.method != "POST":
        return redirect(
            "tasks:task-detail",
            pk=task.pk,
        )

    form = TaskCommentForm(
        request.POST
    )

    if form.is_valid():
        try:
            add_task_comment(
                user=request.user,
                task=task,
                testo=(
                    form.cleaned_data[
                        "testo"
                    ]
                ),
            )

        except (
            PermissionDenied,
            ValidationError,
        ) as exc:
            messages.error(
                request,
                str(exc),
            )

        else:
            messages.success(
                request,
                "Commento aggiunto.",
            )

    else:
        messages.error(
            request,
            "Il commento non può essere vuoto.",
        )

    return redirect(
        "tasks:task-detail",
        pk=task.pk,
    )


# =========================================================
# ELIMINAZIONE
# =========================================================


@login_required
def task_delete_view(
    request,
    pk,
):
    task = get_object_or_404(
        Task.objects.select_related(
            "commessa",
            "commessa__cliente",
            "fase",
            "fase__commessa",
            "assegnato_a",
        ),
        pk=pk,
    )

    if not can_delete_task(
        request.user,
        task,
    ):
        raise PermissionDenied(
            "Non puoi eliminare questa attività."
        )

    if request.method == "POST":
        try:
            delete_task(
                user=request.user,
                task=task,
            )

        except (
            PermissionDenied,
            ValidationError,
        ) as exc:
            messages.error(
                request,
                str(exc),
            )

            return redirect(
                "tasks:task-detail",
                pk=task.pk,
            )

        messages.success(
            request,
            "Attività eliminata correttamente.",
        )

        return redirect(
            "tasks:task-list"
        )

    return render(
        request,
        "tasks/task_confirm_delete.html",
        {
            "task": task,
        },
    )


# =========================================================
# AJAX / JSON — FASI COMMESSA
# =========================================================


@login_required
def project_phases(request):
    commessa_id = request.GET.get("commessa")

    if not commessa_id:
        return JsonResponse({"results": []})

    commessa = (
        manageable_projects_for_user(request.user)
        .filter(pk=commessa_id)
        .first()
    )

    if commessa is None:
        raise PermissionDenied(
            "Non puoi gestire attività su questa commessa."
        )

    fasi = (
        manageable_phases_for_user(request.user)
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


# =========================================================
# AJAX / JSON — ASSEGNATARI FASE
# =========================================================


@login_required
def phase_assignees(request):
    fase_id = request.GET.get("fase")

    if not fase_id:
        return JsonResponse({"results": []})

    fase = (
        manageable_phases_for_user(request.user)
        .filter(pk=fase_id)
        .first()
    )

    if fase is None:
        raise PermissionDenied(
            "Non puoi gestire attività su questa fase."
        )

    utenti = assignable_users_for_phase(
        user=request.user,
        fase=fase,
    )

    return JsonResponse(
        {
            "results": [
                {
                    "id": str(utente.pk),
                    "label": (
                        utente.get_full_name().strip()
                        or utente.email
                    ),
                }
                for utente in utenti
            ]
        }
    )

# =========================================================
# AJAX / JSON — ASSEGNATARI COMMESSA
# =========================================================


@login_required
def project_assignees(request):
    """
    Restituisce gli utenti assegnabili alla commessa.

    Usato dal form Nuova attività quando cambia
    la selezione della commessa.
    """

    commessa_id = request.GET.get(
        "commessa"
    )

    if not commessa_id:
        return JsonResponse(
            {
                "results": [],
            }
        )

    commessa = (
        manageable_projects_for_user(
            request.user
        )
        .filter(
            pk=commessa_id
        )
        .first()
    )

    if commessa is None:
        raise PermissionDenied(
            "Non puoi gestire attività "
            "su questa commessa."
        )

    utenti = assignable_users_for_project(
        user=request.user,
        commessa=commessa,
    )

    results = []

    for utente in utenti:
        nome = (
            utente.get_full_name()
            .strip()
        )

        results.append(
            {
                "id": str(
                    utente.pk
                ),
                "label": (
                    nome
                    or utente.email
                ),
            }
        )

    return JsonResponse(
        {
            "results": results,
        }
    )