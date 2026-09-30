import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch, Q
from django.db import models, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.common.request_security import safe_internal_redirect
from apps.common.mixins import (
    AdminRequiredMixin,
    BusinessUnitEditRequiredMixin,
    BusinessUnitReadRequiredMixin,
    ManagementRequiredMixin,
    PeopleReadRequiredMixin,
    SkillCatalogRequiredMixin,
    SkillMatrixReadRequiredMixin,
)
from .access import (
    business_units_in_scope,
    can_designate_bu_managers,
    can_edit_business_units,
    can_manage_business_unit,
    can_manage_skill_catalog,
    can_manage_skill_matrix,
    can_manage_users,
    is_global_manager,
    managed_business_unit_ids,
    membership_current_q,
    persone_in_scope,
    uuid_valido,
)
from .business_units import (
    capacita_mensile,
    carichi_membri,
    commesse_business_unit,
    indicatori_business_unit,
    responsabili_business_unit,
)
from apps.operations.models import AuditLog, PeriodoMensile
from .forms import (
    BusinessUnitForm,
    ConsulenteCreateForm,
    ConsulenteUpdateForm,
    SkillForm,
    SkillMatrixUserForm,
    UserBusinessUnitForm,
    UserProfileForm,
)
from .models import BusinessUnit, Skill, User, UserBusinessUnit, UserSkill
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
        # Gestione globale: tutte le persone; Responsabile BU: i membri delle
        # proprie Business Unit.
        queryset = persone_in_scope(self.request.user).order_by(
            "last_name",
            "first_name",
            "email",
        )
        if not is_global_manager(self.request.user):
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
        if not is_global_manager(self.request.user):
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
        context["puo_gestire_utenti"] = can_manage_users(self.request.user)
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


class SkillListView(SkillCatalogRequiredMixin, ListView):
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


class SkillCreateView(SkillCatalogRequiredMixin, CreateView):
    model = Skill
    form_class = SkillForm
    template_name = "accounts/skill_form.html"
    success_url = reverse_lazy("accounts:skill-list")

    def form_valid(self, form):
        messages.success(self.request, "Skill creata correttamente.")
        return super().form_valid(form)


class SkillUpdateView(SkillCatalogRequiredMixin, UpdateView):
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

        # Lettura su tutte le risorse (serve a comporre i team); modifica
        # solo sulle persone nel proprio perimetro.
        modificabili = set(
            persone_in_scope(request.user).values_list("pk", flat=True)
        ) if can_manage_skill_matrix(request.user) else set()
        righe = []
        for risorsa in risorse:
            livelli = {
                voce.skill_id: voce for voce in getattr(risorsa, "skill_matrix_prefetched", [])
            }
            righe.append(
                {
                    "risorsa": risorsa,
                    "celle": [livelli.get(skill.pk) for skill in skills],
                    "modificabile": risorsa.pk in modificabili,
                }
            )

        return render(
            request,
            self.template_name,
            {
                "skills": skills,
                "righe": righe,
                "puo_modificare": bool(modificabili),
                "puo_gestire_catalogo": can_manage_skill_catalog(request.user),
            },
        )


class SkillMatrixUserUpdateView(ManagementRequiredMixin, View):
    template_name = "accounts/skill_matrix_user_form.html"

    def _utente(self, pk):
        return get_object_or_404(
            persone_in_scope(self.request.user),
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


def _mese_corrente(request):
    from django.utils import timezone

    valore = request.GET.get("mese", "")
    try:
        anno_str, mese_str = valore.split("-", 1)
        anno, mese = int(anno_str), int(mese_str)
        if 1 <= mese <= 12:
            return anno, mese, f"{anno:04d}-{mese:02d}"
    except (TypeError, ValueError):
        pass
    oggi = timezone.localdate()
    return oggi.year, oggi.month, f"{oggi.year:04d}-{oggi.month:02d}"


class BusinessUnitListView(BusinessUnitReadRequiredMixin, ListView):
    """Elenco BU: tutte per la gestione globale e la DG, le proprie per il Resp. BU."""

    model = BusinessUnit
    template_name = "accounts/business_unit_list.html"
    context_object_name = "business_units"
    paginate_by = 30

    def get_queryset(self):
        queryset = business_units_in_scope(self.request.user).annotate(
            numero_membri=models.Count(
                "membership",
                filter=membership_current_q("membership__"),
                distinct=True,
            ),
            numero_responsabili=models.Count(
                "membership",
                filter=(
                    membership_current_q("membership__")
                    & Q(
                        membership__responsabile=True,
                        membership__utente__ruolo=User.Ruolo.RESPONSABILE_CONSULENZA,
                    )
                ),
                distinct=True,
            ),
            numero_commesse_aperte=models.Count(
                "commesse",
                filter=Q(commesse__stato="APERTA"),
                distinct=True,
            ),
        ).order_by("-attiva", "nome")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(nome__icontains=query) | Q(codice__icontains=query))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["puo_creare"] = can_edit_business_units(user)
        context["puo_gestire_membri"] = bool(
            is_global_manager(user) or managed_business_unit_ids(user)
        )
        gestite = managed_business_unit_ids(user)
        for bu in context["business_units"]:
            bu.gestibile = is_global_manager(user) or bu.pk in gestite
        return context


class BusinessUnitDetailView(BusinessUnitReadRequiredMixin, View):
    """Cruscotto della Business Unit: persone, carichi, commesse e azioni."""

    template_name = "accounts/business_unit_detail.html"

    def get(self, request, pk):
        business_unit = get_object_or_404(business_units_in_scope(request.user), pk=pk)
        anno, mese, valore_mese = _mese_corrente(request)
        puo_gestire = can_manage_business_unit(request.user, business_unit)
        membri = carichi_membri([business_unit.pk], anno, mese)
        capacita = capacita_mensile(anno, mese)
        for voce in membri:
            voce["percentuale"] = round(voce["ore_pianificate"] * 100 / capacita) if capacita else 0
        periodo = PeriodoMensile.objects.filter(anno=anno, mese=mese).first()
        return render(
            request,
            self.template_name,
            {
                "business_unit": business_unit,
                "mese_selezionato": valore_mese,
                "periodo": periodo,
                "periodo_chiuso": bool(
                    periodo and periodo.stato == PeriodoMensile.Stato.CHIUSO
                ),
                "periodo_stato": periodo.get_stato_display() if periodo else "Aperto",
                "indicatori": indicatori_business_unit([business_unit.pk], anno, mese),
                "responsabili": responsabili_business_unit(business_unit),
                "membri": membri,
                "capacita_mese": capacita,
                "commesse": commesse_business_unit([business_unit.pk]),
                "puo_gestire": puo_gestire,
                "puo_modificare_anagrafica": can_edit_business_units(request.user),
                "puo_nominare_responsabili": can_designate_bu_managers(request.user),
            },
        )


class BusinessUnitCreateView(BusinessUnitEditRequiredMixin, CreateView):
    model = BusinessUnit
    form_class = BusinessUnitForm
    template_name = "accounts/business_unit_form.html"

    def get_success_url(self):
        return reverse("accounts:business-unit-detail", args=[self.object.pk])

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Business Unit creata correttamente.")
        return response


class BusinessUnitUpdateView(BusinessUnitEditRequiredMixin, UpdateView):
    model = BusinessUnit
    form_class = BusinessUnitForm
    template_name = "accounts/business_unit_form.html"

    def get_success_url(self):
        return reverse("accounts:business-unit-detail", args=[self.object.pk])

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Business Unit aggiornata correttamente.")
        return response


def _appartenenze_in_scope(user):
    queryset = UserBusinessUnit.objects.select_related("utente", "business_unit")
    if is_global_manager(user):
        return queryset
    return queryset.filter(business_unit_id__in=managed_business_unit_ids(user))


class UserBusinessUnitListView(ManagementRequiredMixin, ListView):
    model = UserBusinessUnit
    template_name = "accounts/user_business_unit_list.html"
    context_object_name = "membership"
    paginate_by = 40

    def get_queryset(self):
        queryset = _appartenenze_in_scope(self.request.user).order_by(
            "business_unit__nome", "utente__last_name", "utente__first_name"
        )
        bu_id = self.request.GET.get("business_unit", "").strip()
        if bu_id:
            bu_id = uuid_valido(bu_id)
            queryset = queryset.filter(business_unit_id=bu_id) if bu_id else queryset.none()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["business_units_filtro"] = business_units_in_scope(user).order_by("nome")
        puo_nominare = can_designate_bu_managers(user)
        for voce in context["membership"]:
            # Le appartenenze da Responsabile sono modificabili solo dall'Admin.
            voce.modificabile = puo_nominare or not voce.responsabile
        return context


class _UserBusinessUnitFormMixin:
    model = UserBusinessUnit
    form_class = UserBusinessUnitForm
    template_name = "accounts/user_business_unit_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = safe_internal_redirect(
            self.request, self.request.GET.get("return_to")
        )
        return context

    def get_success_url(self):
        return_to = safe_internal_redirect(
            self.request,
            self.request.POST.get("return_to") or self.request.GET.get("return_to"),
        )
        if return_to:
            return return_to

        destinazione = self.request.GET.get("next") or self.request.POST.get("next")
        if destinazione == "bu":
            return_bu = uuid_valido(
                self.request.POST.get("return_bu")
                or self.request.GET.get("return_bu")
            )
            if return_bu and business_units_in_scope(self.request.user).filter(pk=return_bu).exists():
                return reverse("accounts:business-unit-detail", args=[return_bu])
            return reverse("accounts:business-unit-detail", args=[self.object.business_unit_id])
        return reverse("accounts:user-business-unit-list")


class UserBusinessUnitCreateView(ManagementRequiredMixin, _UserBusinessUnitFormMixin, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        bu_id = uuid_valido(self.request.GET.get("business_unit"))
        if bu_id and business_units_in_scope(self.request.user).filter(pk=bu_id).exists():
            initial["business_unit"] = bu_id
        return initial

    def form_valid(self, form):
        if not can_manage_business_unit(self.request.user, form.cleaned_data["business_unit"]):
            raise PermissionDenied("Non gestisci questa Business Unit.")
        response = super().form_valid(form)
        messages.success(self.request, "Appartenenza alla Business Unit salvata.")
        return response


class UserBusinessUnitUpdateView(ManagementRequiredMixin, _UserBusinessUnitFormMixin, UpdateView):
    def get_queryset(self):
        queryset = _appartenenze_in_scope(self.request.user)
        if not can_designate_bu_managers(self.request.user):
            queryset = queryset.filter(responsabile=False)
        return queryset

    def form_valid(self, form):
        if not can_manage_business_unit(self.request.user, form.cleaned_data["business_unit"]):
            raise PermissionDenied("Non gestisci questa Business Unit.")
        response = super().form_valid(form)
        messages.success(self.request, "Appartenenza alla Business Unit aggiornata.")
        return response
