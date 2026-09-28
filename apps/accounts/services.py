import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import User

logger = logging.getLogger(__name__)


def _activation_url(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse(
        "account_activation_confirm",
        kwargs={"uidb64": uid, "token": token},
    )
    return f"{settings.SITE_URL}{path}"


def send_account_activation_email(user: User) -> None:
    """Invia (o reinvia) l'invito ad attivare l'account LEFTRACK.

    L'Admin non conosce mai la password: l'utente riceve un link firmato e
    imposta direttamente la propria password. Lo stesso flusso vale anche per
    i nuovi Admin LEF creati da Persone e ruoli: diventano Admin applicativi,
    non superuser Django. Gli account già attivati non possono ricevere un
    nuovo invito di attivazione; per loro resta disponibile il normale flusso
    "Password dimenticata?".
    """

    if user.has_usable_password():
        raise ValidationError(
            "L'account è già stato attivato. Usa il recupero password se necessario."
        )

    # Un account in attesa di attivazione deve rimanere non autenticabile.
    update_fields = []
    if user.is_active:
        user.is_active = False
        update_fields.append("is_active")
    if not user.deve_cambiare_password:
        user.deve_cambiare_password = True
        update_fields.append("deve_cambiare_password")
    if update_fields:
        user.save(update_fields=update_fields)

    activation_url = _activation_url(user)
    context = {
        "user": user,
        "activation_url": activation_url,
    }

    subject = "Attiva il tuo account LEFTRACK"
    text_body = render_to_string(
        "registration/account_activation_email.txt",
        context,
    )
    html_body = render_to_string(
        "registration/account_activation_email.html",
        context,
    )

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")

    sent = message.send(fail_silently=False)
    if sent != 1:
        raise RuntimeError("Il backend email non ha confermato l'invio dell'invito.")

    sent_at = timezone.now()
    User.objects.filter(pk=user.pk).update(invito_inviato_il=sent_at)
    user.invito_inviato_il = sent_at
    logger.info("Invito di attivazione LEFTRACK inviato all'utente %s", user.pk)


@transaction.atomic
def set_user_active(*, attore: User, user: User, active: bool) -> User:
    """Attiva/disattiva un account senza lasciare lavoro operativo orfano."""
    from apps.operations.models import AuditLog
    from apps.planning.models import GiornoPianificato
    from apps.projects.models import Assegnazione

    if not getattr(attore, "is_admin_lef", False):
        raise PermissionDenied("Questa operazione è riservata agli Admin LEF.")

    user = User.objects.select_for_update().get(pk=user.pk)
    active = bool(active)
    if user.is_active == active:
        return user

    if not active:
        if user.ruolo == User.Ruolo.ADMIN:
            if attore.pk == user.pk:
                raise ValidationError(
                    "Non puoi disattivare il tuo stesso account Admin. Usa un altro Admin LEF."
                )
            altri_admin_attivi = (
                User.objects.select_for_update()
                .filter(ruolo=User.Ruolo.ADMIN, is_active=True)
                .exclude(pk=user.pk)
            )
            if not altri_admin_attivi.exists():
                raise ValidationError(
                    "Deve rimanere almeno un Admin LEF attivo nel sistema."
                )

        assegnazioni_attive = Assegnazione.objects.select_for_update().filter(
            consulente=user,
            stato=Assegnazione.Stato.ATTIVA,
        )
        if assegnazioni_attive.exists():
            pm = assegnazioni_attive.filter(
                ruolo_commessa=Assegnazione.Ruolo.PROJECT_MANAGER
            ).exists()
            dettaglio = " incluse responsabilità da Project Manager" if pm else ""
            raise ValidationError(
                "Non puoi disattivare l'utente: esistono assegnazioni operative attive"
                f"{dettaglio}. Concludile o trasferiscile prima."
            )

        sessioni_aperte = GiornoPianificato.objects.select_for_update().filter(
            assegnazione__consulente=user,
            stato_sessione=GiornoPianificato.StatoSessione.PIANIFICATA,
        )
        if sessioni_aperte.exists():
            raise ValidationError(
                "Non puoi disattivare l'utente: esistono sessioni agenda ancora da confermare."
            )

    precedente = {"is_active": user.is_active}
    user.is_active = active
    user.save(update_fields=("is_active",))
    AuditLog.objects.create(
        utente=attore,
        entita="Utente",
        entita_id=user.id,
        azione="RIATTIVAZIONE" if active else "DISATTIVAZIONE",
        valore_precedente=precedente,
        valore_nuovo={"is_active": user.is_active},
        motivazione="Cambio stato account tramite service LEFTRACK.",
    )
    return user
