import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.common.mixins import (
    AdminRequiredMixin,
    PeopleReadRequiredMixin,
    SkillMatrixReadRequiredMixin,
)
from apps.operations.models import AuditLog
from .forms import (
    ConsulenteCreateForm,
    ConsulenteUpdateForm,
    SkillForm,
    SkillMatrixUserForm,
    UserProfileForm,
)
from .models import Skill, User, UserSkill
from .services import send_account_activation_email, set_user_active

logger = logging.getLogger(__name__)


class UserProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Profilo personale: l'utente può aggiornare dati base e avatar, non ruolo/email."""

    model = User
    form_class = UserProfileForm
    template_name = "accounts/profile_form.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse("accounts:profile")

    def form_valid(self, form):
        previous_photo_name = ""
        if self.object and self.object.pk:
            previous_photo_name = (
                User.objects.filter(pk=self.object.pk)
                .values_list("foto_profilo", flat=True)
                .first()
                or ""
            )

        response = super().form_valid(form)

        current_photo_name = self.object.foto_profilo.name if self.object.foto_profilo else ""
        if previous_photo_name and previous_photo_name != current_photo_name:
            storage = self.object._meta.get_field("foto_profilo").storage
            if storage.exists(previous_photo_name):
                storage.delete(previous_photo_name)

        messages.success(self.request, "Profilo aggiornato correttamente.")
        return response


class ConsulenteListView(PeopleReadRequiredMixin, ListView):
    model = User
    template_name = "accounts/consulente_list.html"
    context_object_name = "consulenti"
    paginate_by = 25

    def get_queryset(self):
        queryset = User.objects.order_by(
            "last_name",
            "first_name",
            "email",
        )
        if self.request.user.is_responsabile_consulenza:
            queryset = queryset.filter(
                ruolo__in=(
                    User.Ruolo.CONSULENTE,
                    User.Ruolo.RESPONSABILE_CONSULENZA,
                )
            )
        query = self.request.GET.get("q", "").strip()
        stato = self.request.GET.get("stato", "").strip()
        ruolo = self.request.GET.get("ruolo", "").strip()
        if query:
            queryset = queryset.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
        if ruolo in {choice[0] for choice in User.Ruolo.choices}:
            queryset = queryset.filter(ruolo=ruolo)
        if stato == "attivi":
            queryset = queryset.filter(
                is_active=True,
            ).exclude(password__startswith="!")
        elif stato == "invito":
            queryset = queryset.filter(
                password__startswith="!",
            )
        elif stato == "disattivati":
            queryset = queryset.filter(
                is_active=False,
            ).exclude(password__startswith="!")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_responsabile_consulenza:
            context["ruoli_filtro"] = [
                choice
                for choice in User.Ruolo.choices
                if choice[0]
                in {
                    User.Ruolo.CONSULENTE,
                    User.Ruolo.RESPONSABILE_CONSULENZA,
                }
            ]
        else:
            context["ruoli_filtro"] = list(User.Ruolo.choices)
        context["puo_gestire_utenti"] = self.request.user.is_admin_lef
        return context


class ConsulenteCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = ConsulenteCreateForm
    template_name = "accounts/consulente_form.html"
    success_url = reverse_lazy("accounts:consulente-list")

    def form_valid(self, form):
        self.object = form.save()
        AuditLog.objects.create(
            utente=self.request.user,
            entita="Utente",
            entita_id=self.object.id,
            azione="CREAZIONE",
            valore_precedente=None,
            valore_nuovo={
                "email": self.object.email,
                "ruolo": self.object.ruolo,
                "is_active": self.object.is_active,
            },
            motivazione="Creazione utente da Persone e ruoli.",
        )
        try:
            send_account_activation_email(self.object)
        except Exception:
            logger.exception(
                "Invio automatico dell'invito fallito per l'utente %s",
                self.object.pk,
            )
            messages.warning(
                self.request,
                "Utente creato, ma l'invito di attivazione non è stato inviato. "
                "Verifica l'email/configurazione SMTP e usa 'Reinvia invito'.",
            )
        else:
            messages.success(
                self.request,
                f"Utente creato. Invito di attivazione inviato a {self.object.email}.",
            )
        return HttpResponseRedirect(self.get_success_url())


class ConsulenteUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = ConsulenteUpdateForm
    template_name = "accounts/consulente_form.html"
    success_url = reverse_lazy("accounts:consulente-list")

    def get_queryset(self):
        return User.objects.all()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["attore"] = self.request.user
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        precedente = User.objects.select_for_update().get(pk=form.instance.pk)

        # Ri-verifica sotto lock il vincolo "almeno un Admin attivo" per
        # evitare che due modifiche concorrenti retrocedano gli ultimi Admin.
        nuovo_ruolo = form.cleaned_data["ruolo"]
        if precedente.ruolo == User.Ruolo.ADMIN and nuovo_ruolo != User.Ruolo.ADMIN:
            admin_attivi = list(
                User.objects.select_for_update()
                .filter(ruolo=User.Ruolo.ADMIN, is_active=True)
                .order_by("pk")
            )
            if precedente.is_active and not any(
                admin.pk != precedente.pk for admin in admin_attivi
            ):
                form.add_error(
                    "ruolo",
                    "Deve rimanere almeno un Admin LEF attivo nel sistema.",
                )
                return self.form_invalid(form)

        pending_email_changed = (
            "email" in form.changed_data and form.instance.is_pending_activation
        )
        self.object = form.save()

        AuditLog.objects.create(
            utente=self.request.user,
            entita="Utente",
            entita_id=self.object.id,
            azione="AGGIORNAMENTO",
            valore_precedente={
                "email": precedente.email,
                "ruolo": precedente.ruolo,
                "is_active": precedente.is_active,
            },
            valore_nuovo={
                "email": self.object.email,
                "ruolo": self.object.ruolo,
                "is_active": self.object.is_active,
            },
            motivazione="Aggiornamento utente da Persone e ruoli.",
        )

        if pending_email_changed:
            self.object.invito_inviato_il = None
            self.object.save(update_fields=("invito_inviato_il",))
            try:
                send_account_activation_email(self.object)
            except Exception:
                logger.exception(
                    "Reinvio dopo modifica email fallito per l'utente %s",
                    self.object.pk,
                )
                messages.warning(
                    self.request,
                    "Dati aggiornati, ma il nuovo invito non è stato inviato. "
                    "Usa 'Reinvia invito'.",
                )
            else:
                messages.success(
                    self.request,
                    f"Dati aggiornati e nuovo invito inviato a {self.object.email}.",
                )
        else:
            messages.success(self.request, "Dati dell'utente aggiornati.")

        return HttpResponseRedirect(self.get_success_url())


class ConsulenteToggleActiveView(AdminRequiredMixin, View):
    def post(self, request, pk):
        consulente = get_object_or_404(User, pk=pk)

        if not consulente.is_active and consulente.is_pending_activation:
            messages.warning(
                request,
                "L'account è in attesa di attivazione. Usa 'Reinvia invito' invece di riattivarlo manualmente.",
            )
            return HttpResponseRedirect(reverse("accounts:consulente-list"))

        try:
            consulente = set_user_active(
                attore=request.user,
                user=consulente,
                active=not consulente.is_active,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            stato = "riattivato" if consulente.is_active else "disattivato"
            messages.success(request, f"Utente {stato} correttamente.")
        return HttpResponseRedirect(reverse("accounts:consulente-list"))


class ConsulenteResendInviteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        consulente = get_object_or_404(User, pk=pk)

        try:
            send_account_activation_email(consulente)
        except ValidationError as exc:
            messages.warning(request, "; ".join(exc.messages))
        except Exception:
            logger.exception(
                "Reinvio dell'invito fallito per l'utente %s",
                consulente.pk,
            )
            messages.error(
                request,
                "Invito non inviato. Verifica l'indirizzo email e la configurazione SMTP.",
            )
        else:
            messages.success(
                request,
                f"Invito di attivazione reinviato a {consulente.email}.",
            )

        return HttpResponseRedirect(reverse("accounts:consulente-list"))


class SkillListView(AdminRequiredMixin, ListView):
    model = Skill
    template_name = "accounts/skill_list.html"
    context_object_name = "skills"
    paginate_by = 50

    def get_queryset(self):
        queryset = Skill.objects.order_by("categoria", "nome")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(nome__icontains=query)
                | Q(categoria__icontains=query)
                | Q(descrizione__icontains=query)
            )
        return queryset


class SkillCreateView(AdminRequiredMixin, CreateView):
    model = Skill
    form_class = SkillForm
    template_name = "accounts/skill_form.html"
    success_url = reverse_lazy("accounts:skill-list")

    def form_valid(self, form):
        messages.success(self.request, "Skill creata correttamente.")
        return super().form_valid(form)


class SkillUpdateView(AdminRequiredMixin, UpdateView):
    model = Skill
    form_class = SkillForm
    template_name = "accounts/skill_form.html"
    success_url = reverse_lazy("accounts:skill-list")

    def form_valid(self, form):
        messages.success(self.request, "Skill aggiornata correttamente.")
        return super().form_valid(form)


class SkillMatrixView(SkillMatrixReadRequiredMixin, View):
    template_name = "accounts/skill_matrix.html"

    def get(self, request):
        skills = list(Skill.objects.filter(attiva=True).order_by("categoria", "nome"))
        risorse = list(
            User.objects.filter(
                ruolo__in=(
                    User.Ruolo.CONSULENTE,
                    User.Ruolo.RESPONSABILE_CONSULENZA,
                )
            )
            .prefetch_related(
                Prefetch(
                    "skill_matrix",
                    queryset=UserSkill.objects.select_related("skill"),
                    to_attr="skill_matrix_prefetched",
                )
            )
            .order_by("last_name", "first_name", "email")
        )

        righe = []
        for risorsa in risorse:
            livelli = {
                voce.skill_id: voce for voce in getattr(risorsa, "skill_matrix_prefetched", [])
            }
            righe.append(
                {
                    "risorsa": risorsa,
                    "celle": [livelli.get(skill.pk) for skill in skills],
                }
            )

        return render(
            request,
            self.template_name,
            {
                "skills": skills,
                "righe": righe,
                "puo_modificare": request.user.is_admin_lef,
            },
        )


class SkillMatrixUserUpdateView(AdminRequiredMixin, View):
    template_name = "accounts/skill_matrix_user_form.html"

    def _utente(self, pk):
        return get_object_or_404(
            User,
            pk=pk,
            ruolo__in=(
                User.Ruolo.CONSULENTE,
                User.Ruolo.RESPONSABILE_CONSULENZA,
            ),
        )

    def get(self, request, pk):
        utente = self._utente(pk)
        form = SkillMatrixUserForm(utente=utente)
        return render(request, self.template_name, {"form": form, "utente": utente})

    def post(self, request, pk):
        utente = self._utente(pk)
        form = SkillMatrixUserForm(request.POST, utente=utente)
        if form.is_valid():
            form.save()
            messages.success(request, f"Skill matrix aggiornata per {utente}.")
            return HttpResponseRedirect(reverse("accounts:skill-matrix"))
        return render(request, self.template_name, {"form": form, "utente": utente})
