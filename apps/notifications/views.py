from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)


from .selectors import (
    notification_for_user,
    notification_summary,
    notifications_for_user,
)
from .services import (
    mark_all_notifications_read,
    mark_notification_read,
    mark_notification_unread,
)
from .models import Notification
from .forms import NotificationPreferenceForm
from .models import NotificationPreference


# =========================================================
# ELENCO NOTIFICHE
# =========================================================


@login_required
def notification_list(request):
    """
    Pagina con tutte le notifiche dell'utente autenticato.
    """

    unread_only = (
        request.GET.get("non_lette")
        == "1"
    )

    tipo = request.GET.get(
        "tipo",
        "",
    )

    queryset = notifications_for_user(
        user=request.user,
        unread_only=unread_only,
    )

    if (
        tipo
        and tipo in Notification.Tipo.values
    ):
        queryset = queryset.filter(
            tipo=tipo
        )

    context = {
        "notifications": queryset,

        "summary": notification_summary(
            user=request.user
        ),

        "tipi": Notification.Tipo.choices,

        "tipo_selezionato": tipo,

        "unread_only": unread_only,
    }

    return render(
        request,
        "notifications/notification_list.html",
        context,
    )


# =========================================================
# APERTURA NOTIFICA
# =========================================================


@login_required
def notification_open(
    request,
    pk,
):
    """
    Apre una notifica.

    - verifica che appartenga all'utente;
    - la segna automaticamente come letta;
    - se collegata a un Task porta al dettaglio Task;
    - altrimenti torna all'elenco notifiche.
    """

    notification = get_object_or_404(
        notification_for_user(
            user=request.user,
            pk=pk,
        )
    )

    notification = mark_notification_read(
        user=request.user,
        notification=notification,
    )

    if notification.task_id:
        return redirect(
            "tasks:task-detail",
            pk=notification.task_id,
        )

    commessa = notification.commessa
    if commessa is not None:
        return redirect(
            "projects:commessa-teamwork",
            pk=commessa.pk,
        )

    return redirect("notifications:notification-list")


# =========================================================
# SEGNA COME LETTA
# =========================================================


@login_required
def notification_mark_read(
    request,
    pk,
):
    notification = get_object_or_404(
        notification_for_user(
            user=request.user,
            pk=pk,
        )
    )

    if request.method != "POST":
        return redirect(
            "notifications:notification-list"
        )

    try:
        mark_notification_read(
            user=request.user,
            notification=notification,
        )

    except PermissionDenied:
        raise

    messages.success(
        request,
        "Notifica segnata come letta.",
    )

    return redirect(
        "notifications:notification-list"
    )


# =========================================================
# SEGNA COME NON LETTA
# =========================================================


@login_required
def notification_mark_unread(
    request,
    pk,
):
    notification = get_object_or_404(
        notification_for_user(
            user=request.user,
            pk=pk,
        )
    )

    if request.method != "POST":
        return redirect(
            "notifications:notification-list"
        )

    try:
        mark_notification_unread(
            user=request.user,
            notification=notification,
        )

    except PermissionDenied:
        raise

    messages.success(
        request,
        "Notifica segnata come non letta.",
    )

    return redirect(
        "notifications:notification-list"
    )


# =========================================================
# SEGNA TUTTE COME LETTE
# =========================================================


@login_required
def notification_mark_all_read(
    request,
):
    if request.method != "POST":
        return redirect(
            "notifications:notification-list"
        )

    aggiornate = mark_all_notifications_read(
        user=request.user
    )

    if aggiornate:
        messages.success(
            request,
            (
                f"{aggiornate} "
                "notifiche segnate come lette."
            ),
        )

    else:
        messages.info(
            request,
            "Non ci sono notifiche da aggiornare.",
        )

    return redirect(
        "notifications:notification-list"
    )



@login_required
def notification_preferences(request):

    preference, created = (
        NotificationPreference.objects
        .get_or_create(
            user=request.user
        )
    )

    if request.method == "POST":

        form = NotificationPreferenceForm(
            request.POST,
            instance=preference,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Preferenze notifiche aggiornate.",
            )

            return redirect(
                "notifications:preferences"
            )

    else:

        form = NotificationPreferenceForm(
            instance=preference
        )


    return render(
        request,
        "notifications/preferences.html",
        {
            "form": form,
        },
    )