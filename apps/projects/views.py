from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.common.request_security import safe_internal_redirect
from apps.common.mixins import (
    AssignmentsManagementRequiredMixin,
    ClientManagementRequiredMixin,
    ManagementRequiredMixin,
    FinanceManagementRequiredMixin,
    ReferencePortfolioReadRequiredMixin,
    AssignmentsRegisterReadRequiredMixin,
    ProjectManagementRequiredMixin,
)
from apps.accounts.access import (
    business_units_in_scope,
    can_edit_commessa_anagrafica,
    can_manage_assignments,
    can_manage_clients,
    can_manage_commessa,
    can_manage_projects,
    can_view_tasks_portfolio,
    can_view_teamwork_without_assignment,
    commesse_in_scope,
    commesse_visibili,
    is_manager,
    uuid_valido,
)
from apps.operations.models import AuditLog
from apps.phases.models import FaseCommessa

from .forms import (
    AssegnazioneForm,
    ClienteForm,
    CommessaForm,
    HandoverCommessaForm,
    TariffaAssegnazioneForm,
    WorkflowCommessaForm,
)

from .models import (
    Assegnazione,
    Cliente,
    Commessa,
    TariffaAssegnazione,
)

from .services import (
    agenda_progress,
    assegnazione_snapshot,
    chiudi_commessa,
    riapri_commessa,
    set_assegnazione_stato,
    set_commessa_workflow,
    sync_general_phase_dates,
    update_handover,
    verifica_tariffa_periodi_aperti,
)


def _return_to_origin_url(request, instance=None):
    """Ritorno controllato alla schermata da cui è partita un'azione.

    Preferisce ``return_to`` quando è un URL interno validato: così vengono
    preservati anche filtri e mese selezionato. Mantiene i token legacy ``bu``
    e ``home-responsabile`` come fallback compatibile.
    """
    return_to = safe_internal_redirect(
        request, request.POST.get("return_to") or request.GET.get("return_to")
    )
    if return_to:
        return return_to

    token = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if token == "home-responsabile":
        return reverse("home")
    if token != "bu":
        return None

    # Se il form nasce da un cruscotto BU, il contesto esplicito di origine
    # ha priorita anche se l'oggetto viene riclassificato durante l'azione.
    bu_id = uuid_valido(
        request.POST.get("return_bu")
        or request.GET.get("return_bu")
        or request.GET.get("business_unit")
    )
    if bu_id and business_units_in_scope(request.user).filter(pk=bu_id).exists():
        return reverse("accounts:business-unit-detail", args=[bu_id])

    if instance is not None:
        bu_id = getattr(instance, "business_unit_id", None)
        if bu_id is None:
            commessa = getattr(instance, "commessa", None)
            bu_id = getattr(commessa, "business_unit_id", None)
    if bu_id and business_units_in_scope(request.user).filter(pk=bu_id).exists():
        return reverse("accounts:business-unit-detail", args=[bu_id])
    return None


class ClienteListView(ReferencePortfolioReadRequiredMixin, ListView):
    model = Cliente
    template_name = "projects/cliente_list.html"
    context_object_name = "clienti"
    paginate_by = 25

    def get_queryset(self):
        queryset = Cliente.objects.annotate(
            numero_commesse=Count("commesse"),
        ).order_by("ragione_sociale")
        query = self.request.GET.get("q", "").strip()
        stato = self.request.GET.get("stato", "").strip()
        if query:
            queryset = queryset.filter(
                Q(ragione_sociale__icontains=query)
                | Q(partita_iva__icontains=query)
                | Q(referente__icontains=query)
            )
        if stato == "attivi":
            queryset = queryset.filter(attivo=True)
        elif stato == "disattivati":
            queryset = queryset.filter(attivo=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["puo_modificare"] = can_manage_clients(self.request.user)
        return context


class ClienteCreateView(ClientManagementRequiredMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "projects/cliente_form.html"
    success_url = reverse_lazy("projects:cliente-list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente creato correttamente.")
        return super().form_valid(form)


class ClienteUpdateView(ClientManagementRequiredMixin, UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "projects/cliente_form.html"
    success_url = reverse_lazy("projects:cliente-list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente aggiornato correttamente.")
        return super().form_valid(form)


class ClienteToggleActiveView(ClientManagementRequiredMixin, View):
    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        cliente.attivo = not cliente.attivo
        cliente.save(update_fields=("attivo", "updated_at"))
        stato = "riattivato" if cliente.attivo else "disattivato"
        messages.success(request, f"Cliente {stato} correttamente.")
        return HttpResponseRedirect(reverse("projects:cliente-list"))


class CommessaListView(ReferencePortfolioReadRequiredMixin, ListView):
    model = Commessa
    template_name = "projects/commessa_list.html"
    context_object_name = "commesse"
    paginate_by = 25

    def get_queryset(self):
        queryset = (
            commesse_visibili(self.request.user).select_related("cliente", "business_unit")
            .annotate(
                assegnazioni_attive=Count(
                    "assegnazioni",
                    filter=Q(assegnazioni__stato=Assegnazione.Stato.ATTIVA),
                ),
                ore_assegnate=Sum(
                    "assegnazioni__ore_previste",
                    filter=Q(assegnazioni__stato=Assegnazione.Stato.ATTIVA),
                ),
            )
            .order_by("-data_inizio", "codice")
        )
        query = self.request.GET.get("q", "").strip()
        stato = self.request.GET.get("stato", "").strip()
        cliente_id = self.request.GET.get("cliente", "").strip()
        workflow = self.request.GET.get("workflow", "").strip()
        business_unit = self.request.GET.get("bu", "").strip()
        if business_unit == "nessuna":
            queryset = queryset.filter(business_unit__isnull=True)
        elif business_unit:
            business_unit = uuid_valido(business_unit)
            queryset = (
                queryset.filter(business_unit_id=business_unit)
                if business_unit
                else queryset.none()
            )
        if query:
            queryset = queryset.filter(
                Q(codice__icontains=query)
                | Q(descrizione__icontains=query)
                | Q(cliente__ragione_sociale__icontains=query)
            )
        if stato in {Commessa.Stato.APERTA, Commessa.Stato.CHIUSA}:
            queryset = queryset.filter(stato=stato)
        if cliente_id:
            queryset = queryset.filter(cliente_id=cliente_id)
        if workflow in {choice[0] for choice in Commessa.WorkflowStato.choices}:
            queryset = queryset.filter(workflow_stato=workflow)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clienti_filtro"] = Cliente.objects.order_by("ragione_sociale")
        context["workflow_stati"] = Commessa.WorkflowStato.choices
        user = self.request.user
        context["business_units_filtro"] = business_units_in_scope(user).order_by("nome")
        for commessa in context["commesse"]:
            commessa.agenda_progress = agenda_progress(commessa)
            commessa.riga_modificabile = can_edit_commessa_anagrafica(user, commessa)
            commessa.riga_stato_modificabile = can_manage_commessa(user, commessa)
        context["puo_modificare"] = can_manage_projects(user)
        context["puo_cambiare_stato"] = is_manager(user)
        return context


class _CommessaFormUserMixin:
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


class CommessaCreateView(ProjectManagementRequiredMixin, _CommessaFormUserMixin, CreateView):
    model = Commessa
    form_class = CommessaForm
    template_name = "projects/commessa_form.html"
    success_url = reverse_lazy("projects:commessa-list")

    def get_success_url(self):
        return _return_to_origin_url(self.request, self.object) or str(self.success_url)

    def get_initial(self):
        initial = super().get_initial()
        bu_id = uuid_valido(self.request.GET.get("business_unit"))
        if bu_id and business_units_in_scope(self.request.user).filter(pk=bu_id).exists():
            initial["business_unit"] = bu_id
        return initial

    def form_valid(self, form):
        # Workflow e handover non sono mutabili dal form anagrafico: seguono
        # esclusivamente i service dedicati e il relativo audit.
        messages.success(self.request, "Commessa creata correttamente.")
        return super().form_valid(form)


class CommessaUpdateView(ProjectManagementRequiredMixin, _CommessaFormUserMixin, UpdateView):
    model = Commessa
    form_class = CommessaForm
    template_name = "projects/commessa_form.html"
    success_url = reverse_lazy("projects:commessa-list")

    def get_success_url(self):
        return _return_to_origin_url(self.request, self.object) or str(self.success_url)

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "is_commerciale", False):
            return Commessa.objects.all()
        # Responsabile BU: solo le commesse della propria Business Unit.
        return commesse_in_scope(user)

    @transaction.atomic
    def form_valid(self, form):
        # Ordine di lock condiviso: Commessa -> Fasi -> Assegnazioni.
        # Revalidiamo sotto lock per evitare che planning/timesheet/task vengano
        # creati tra la validazione HTTP e il salvataggio delle nuove date.
        commessa = Commessa.objects.select_for_update().get(pk=form.instance.pk)
        list(
            FaseCommessa.objects.select_for_update()
            .filter(commessa=commessa)
            .values_list("pk", flat=True)
        )
        list(
            Assegnazione.objects.select_for_update()
            .filter(commessa=commessa)
            .values_list("pk", flat=True)
        )

        locked_form = self.form_class(
            self.request.POST, instance=commessa, user=self.request.user
        )
        if not locked_form.is_valid():
            return self.form_invalid(locked_form)

        response = super().form_valid(locked_form)
        # La fase tecnica Generale segue sempre il perimetro temporale della
        # commessa. Le altre fasi sono validate dal CommessaForm prima del save.
        sync_general_phase_dates(self.object)
        messages.success(self.request, "Commessa aggiornata correttamente.")
        return response


class CommessaToggleStateView(ManagementRequiredMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        commessa = get_object_or_404(commesse_in_scope(request.user), pk=pk)
        try:
            if commessa.stato == Commessa.Stato.APERTA:
                chiudi_commessa(attore=request.user, commessa=commessa)
                messaggio = (
                    "Commessa chiusa: tutte le sessioni agenda risultano confermate "
                    "e collegate al timesheet."
                )
            else:
                riapri_commessa(attore=request.user, commessa=commessa)
                messaggio = "Commessa riaperta correttamente."
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, messaggio)
        return HttpResponseRedirect(reverse("projects:commessa-list"))


class AssegnazioneListView(AssignmentsRegisterReadRequiredMixin, ListView):
    model = Assegnazione
    template_name = "projects/assegnazione_list.html"
    context_object_name = "assegnazioni"
    paginate_by = 30

    def get_queryset(self):
        queryset = Assegnazione.objects.filter(
            commessa__in=commesse_in_scope(self.request.user)
        ).select_related(
            "consulente",
            "commessa",
            "commessa__cliente",
            "commessa__business_unit",
            "fase",
        ).order_by("commessa__codice", "fase__ordine", "fase__nome", "consulente__last_name")
        query = self.request.GET.get("q", "").strip()
        stato = self.request.GET.get("stato", "").strip()
        commessa_id = self.request.GET.get("commessa", "").strip()
        if query:
            queryset = queryset.filter(
                Q(consulente__first_name__icontains=query)
                | Q(consulente__last_name__icontains=query)
                | Q(consulente__email__icontains=query)
                | Q(commessa__codice__icontains=query)
            )
        if stato in {Assegnazione.Stato.ATTIVA, Assegnazione.Stato.CONCLUSA}:
            queryset = queryset.filter(stato=stato)
        if commessa_id:
            commessa_id = uuid_valido(commessa_id)
            queryset = queryset.filter(commessa_id=commessa_id) if commessa_id else queryset.none()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["commesse_filtro"] = commesse_in_scope(self.request.user).order_by("codice")
        context["puo_modificare"] = can_manage_assignments(self.request.user)
        return context

class FasiPerCommessaView(ManagementRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        commessa_id = uuid_valido(request.GET.get("commessa"))

        if not commessa_id:
            return JsonResponse({"fasi": []})

        fasi = (
            FaseCommessa.objects
            .filter(
                commessa_id=commessa_id,
                commessa__in=commesse_in_scope(request.user),
            )
            .order_by("ordine", "nome")
        )

        return JsonResponse(
            {
                "fasi": [
                    {
                        "id": str(fase.pk),
                        "nome": fase.nome,
                    }
                    for fase in fasi
                ]
            }
        )

class _AssegnazioneFormUserMixin:
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


class AssegnazioneCreateView(AssignmentsManagementRequiredMixin, _AssegnazioneFormUserMixin, CreateView):
    model = Assegnazione
    form_class = AssegnazioneForm
    template_name = "projects/assegnazione_form.html"
    success_url = reverse_lazy("projects:assegnazione-list")

    def get_success_url(self):
        return _return_to_origin_url(self.request, self.object) or str(self.success_url)

    def get_initial(self):
        initial = super().get_initial()
        commessa_id = uuid_valido(self.request.GET.get("commessa"))
        if commessa_id and commesse_in_scope(self.request.user).filter(pk=commessa_id).exists():
            initial["commessa"] = commessa_id
        return initial

    @transaction.atomic
    def form_valid(self, form):
        commessa = Commessa.objects.select_for_update().get(
            pk=form.cleaned_data["commessa"].pk
        )
        fase = FaseCommessa.objects.select_for_update().get(
            pk=form.cleaned_data["fase"].pk
        )
        if fase.commessa_id != commessa.pk:
            form.add_error("fase", "La fase non appartiene alla commessa selezionata.")
            return self.form_invalid(form)

        # Il primo is_valid() è avvenuto prima dei lock. Ripetiamo la validazione
        # nella stessa transazione per coprire modifiche concorrenti di Commessa/Fase.
        locked_form = self.form_class(self.request.POST, user=self.request.user)
        if not locked_form.is_valid():
            return self.form_invalid(locked_form)

        response = super().form_valid(locked_form)
        AuditLog.objects.create(
            utente=self.request.user,
            entita="Assegnazione",
            entita_id=self.object.id,
            azione="CREAZIONE",
            valore_precedente=None,
            valore_nuovo=assegnazione_snapshot(self.object),
            motivazione="Creazione assegnazione da interfaccia amministrativa.",
        )
        messages.success(self.request, "Assegnazione creata correttamente.")
        return response


class AssegnazioneUpdateView(AssignmentsManagementRequiredMixin, _AssegnazioneFormUserMixin, UpdateView):
    model = Assegnazione
    form_class = AssegnazioneForm
    template_name = "projects/assegnazione_form.html"
    success_url = reverse_lazy("projects:assegnazione-list")

    def get_success_url(self):
        return _return_to_origin_url(self.request, self.object) or str(self.success_url)

    def get_queryset(self):
        return Assegnazione.objects.filter(commessa__in=commesse_in_scope(self.request.user))

    @transaction.atomic
    def form_valid(self, form):
        # Lock canonico: Commesse -> Fasi -> Assegnazione.
        # Il ModelForm originale è già stato validato, ma la sua instance è stata
        # mutata con i valori POST; recuperiamo quindi dal DB l'identità corrente.
        riferimento = (
            Assegnazione.objects.filter(pk=form.instance.pk)
            .values("commessa_id", "fase_id")
            .get()
        )
        target_commessa_id = form.cleaned_data["commessa"].pk
        target_fase_id = form.cleaned_data["fase"].pk

        commessa_ids = {riferimento["commessa_id"], target_commessa_id}
        fase_ids = {riferimento["fase_id"], target_fase_id}

        list(
            Commessa.objects.select_for_update()
            .filter(pk__in=commessa_ids)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        list(
            FaseCommessa.objects.select_for_update()
            .filter(pk__in=fase_ids)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        assegnazione = (
            Assegnazione.objects.select_for_update()
            .select_related("commessa", "fase", "consulente")
            .get(pk=form.instance.pk)
        )

        # Se un'altra transazione ha spostato l'assegnazione tra il primo read
        # e l'acquisizione dei lock, non inseguiamo nuovi lock fuori ordine: il
        # client deve ricaricare e riprovare sul dato corrente.
        if (
            assegnazione.commessa_id != riferimento["commessa_id"]
            or assegnazione.fase_id != riferimento["fase_id"]
        ):
            form.add_error(
                None,
                "L'assegnazione è stata modificata da un altro utente. "
                "Ricarica la pagina e riprova.",
            )
            return self.form_invalid(form)

        precedente = assegnazione_snapshot(assegnazione)
        locked_form = self.form_class(
            self.request.POST, instance=assegnazione, user=self.request.user
        )
        if not locked_form.is_valid():
            return self.form_invalid(locked_form)

        response = super().form_valid(locked_form)
        nuovo = assegnazione_snapshot(self.object)
        if nuovo != precedente:
            AuditLog.objects.create(
                utente=self.request.user,
                entita="Assegnazione",
                entita_id=self.object.id,
                azione="MODIFICA",
                valore_precedente=precedente,
                valore_nuovo=nuovo,
                motivazione="Modifica assegnazione da interfaccia amministrativa.",
            )
        messages.success(self.request, "Assegnazione aggiornata correttamente.")
        return response


class AssegnazioneToggleStateView(AssignmentsManagementRequiredMixin, View):
    def post(self, request, pk):
        assegnazione = get_object_or_404(
            Assegnazione.objects.filter(commessa__in=commesse_in_scope(request.user)),
            pk=pk,
        )
        nuovo_stato = (
            Assegnazione.Stato.CONCLUSA
            if assegnazione.stato == Assegnazione.Stato.ATTIVA
            else Assegnazione.Stato.ATTIVA
        )
        try:
            set_assegnazione_stato(
                attore=request.user,
                assegnazione=assegnazione,
                nuovo_stato=nuovo_stato,
            )
        except (ValidationError, IntegrityError) as exc:
            messaggio = (
                "; ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else (
                    "Non è possibile riattivare l'assegnazione: ne esiste già "
                    "una attiva per lo stesso consulente e la stessa fase."
                )
            )
            messages.error(request, messaggio)
        else:
            messaggio = (
                "Assegnazione riattivata correttamente."
                if nuovo_stato == Assegnazione.Stato.ATTIVA
                else "Assegnazione conclusa correttamente."
            )
            messages.success(request, messaggio)
        return HttpResponseRedirect(reverse("projects:assegnazione-list"))



class TariffaListView(FinanceManagementRequiredMixin, ListView):
    model = TariffaAssegnazione
    template_name = "projects/tariffa_list.html"
    context_object_name = "tariffe"
    paginate_by = 40

    def get_queryset(self):
        queryset = TariffaAssegnazione.objects.filter(
            assegnazione__commessa__in=commesse_in_scope(self.request.user)
        ).select_related(
            "assegnazione",
            "assegnazione__consulente",
            "assegnazione__commessa",
            "assegnazione__commessa__cliente",
            "assegnazione__fase",
            "creata_da",
        ).order_by(
            "assegnazione__commessa__codice",
            "assegnazione__fase__ordine",
            "assegnazione__fase__nome",
            "assegnazione__consulente__last_name",
            "tipo_attivita",
            "-valida_dal",
        )

        query = self.request.GET.get("q", "").strip()
        attivita = self.request.GET.get("attivita", "").strip()
        commessa_id = self.request.GET.get("commessa", "").strip()

        if query:
            queryset = queryset.filter(
                Q(assegnazione__consulente__first_name__icontains=query)
                | Q(assegnazione__consulente__last_name__icontains=query)
                | Q(assegnazione__consulente__email__icontains=query)
                | Q(assegnazione__commessa__codice__icontains=query)
                | Q(
                    assegnazione__commessa__cliente__ragione_sociale__icontains=query
                )
            )
        if attivita in {
            TariffaAssegnazione.TipoAttivita.FORMAZIONE,
            TariffaAssegnazione.TipoAttivita.CONSULENZA,
        }:
            queryset = queryset.filter(tipo_attivita=attivita)
        if commessa_id:
            queryset = queryset.filter(
                assegnazione__commessa_id=commessa_id
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["commesse_filtro"] = commesse_in_scope(self.request.user).order_by("codice")
        context["tipi_attivita"] = (
            TariffaAssegnazione.TipoAttivita.choices
        )
        return context


class TariffaCreateView(FinanceManagementRequiredMixin, CreateView):
    model = TariffaAssegnazione
    form_class = TariffaAssegnazioneForm
    template_name = "projects/tariffa_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        mese = self.request.GET.get("mese")

        if mese:
            return f"{reverse_lazy('operations:periodo-detail')}?mese={mese}"

        return str(reverse_lazy("projects:tariffa-list"))

    def get_initial(self):
        initial = super().get_initial()
        assegnazione_id = self.request.GET.get("assegnazione")
        tipo_attivita = self.request.GET.get("tipo_attivita")
        valida_dal = self.request.GET.get("valida_dal")
        if assegnazione_id:
            initial["assegnazione"] = assegnazione_id
        if tipo_attivita:
            initial["tipo_attivita"] = tipo_attivita
        if valida_dal:
            initial["valida_dal"] = valida_dal
        return initial

    @transaction.atomic
    def form_valid(self, form):
        try:
            # Ripete il controllo sotto lock: tra la validazione del form e il
            # save un altro processo non può chiudere il periodo interessato.
            verifica_tariffa_periodi_aperti(
                assegnazione=form.cleaned_data["assegnazione"],
                tipo_attivita=form.cleaned_data["tipo_attivita"],
                valida_dal=form.cleaned_data["valida_dal"],
                lock=True,
            )
        except ValidationError as exc:
            form.add_error("valida_dal", "; ".join(exc.messages))
            return self.form_invalid(form)

        # Il protocollo di lock dei periodi viene prima dell'assegnazione, come
        # nelle mutazioni timesheet, per evitare inversioni e deadlock.
        assegnazione = (
            Assegnazione.objects.select_for_update()
            .select_related("commessa", "fase")
            .get(pk=form.cleaned_data["assegnazione"].pk)
        )
        valida_dal = form.cleaned_data["valida_dal"]
        if valida_dal < assegnazione.data_inizio:
            form.add_error(
                "valida_dal",
                "La tariffa non può iniziare prima dell'assegnazione.",
            )
            return self.form_invalid(form)
        if assegnazione.data_fine and valida_dal > assegnazione.data_fine:
            form.add_error(
                "valida_dal",
                "La tariffa non può iniziare dopo la fine dell'assegnazione.",
            )
            return self.form_invalid(form)

        form.instance.assegnazione = assegnazione
        form.instance.creata_da = self.request.user
        response = super().form_valid(form)

        AuditLog.objects.create(
            utente=self.request.user,
            entita="TariffaAssegnazione",
            entita_id=self.object.id,
            azione="CREAZIONE",
            valore_precedente=None,
            valore_nuovo={
                "assegnazione_id": str(self.object.assegnazione_id),
                "tipo_attivita": self.object.tipo_attivita,
                "tariffa_oraria": str(self.object.tariffa_oraria),
                "valida_dal": self.object.valida_dal.isoformat(),
            },
            motivazione=(
                "Inserimento di una nuova decorrenza tariffaria."
            ),
        )
        messages.success(
            self.request,
            "Nuova tariffa storica registrata correttamente.",
        )
        return response


@login_required
def commessa_handover(request, pk):
    """Presa in carico e conferma handover da Admin o PM della commessa."""
    commessa = get_object_or_404(Commessa.objects.select_related("cliente"), pk=pk)

    from apps.projects.permissions import is_active_pm

    # is_active_pm include la supervisione (Admin, Amministrazione, Resp. BU).
    if not is_active_pm(request.user, commessa):
        raise PermissionDenied(
            "La presa in carico dell'handover è riservata al PM della commessa."
        )

    if request.method == "POST":
        form = HandoverCommessaForm(request.POST, instance=commessa)
        if form.is_valid():
            try:
                commessa = update_handover(
                    attore=request.user,
                    commessa=commessa,
                    completato=form.cleaned_data["handover_completato"],
                    note=form.cleaned_data["handover_note"],
                )
            except (ValidationError, PermissionDenied) as exc:
                form.add_error(None, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
            else:
                messages.success(request, "Handover aggiornato correttamente.")
                return HttpResponseRedirect(
                    reverse("projects:commessa-teamwork", args=[commessa.pk])
                )
    else:
        form = HandoverCommessaForm(instance=commessa)

    return render(
        request,
        "projects/commessa_handover.html",
        {"commessa": commessa, "form": form},
    )


@login_required
def commessa_workflow(request, pk):
    """Transizione auditata del lifecycle, riservata ad Admin e PM della commessa."""
    commessa = get_object_or_404(Commessa.objects.select_related("cliente"), pk=pk)
    from apps.projects.permissions import is_active_pm

    if not is_active_pm(request.user, commessa):
        raise PermissionDenied(
            "La gestione del workflow è riservata al PM della commessa e alla gestione "
            "(Admin, Amministrazione, Responsabile della Business Unit)."
        )

    if request.method == "POST":
        form = WorkflowCommessaForm(request.POST)
        if form.is_valid():
            try:
                commessa = set_commessa_workflow(
                    attore=request.user,
                    commessa=commessa,
                    nuovo_stato=form.cleaned_data["workflow_stato"],
                    motivazione=form.cleaned_data["motivazione"],
                )
            except (ValidationError, PermissionDenied) as exc:
                form.add_error(
                    None,
                    "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc),
                )
            else:
                messages.success(request, "Workflow della commessa aggiornato correttamente.")
                return HttpResponseRedirect(reverse("projects:commessa-teamwork", args=[commessa.pk]))
    else:
        form = WorkflowCommessaForm(initial={"workflow_stato": commessa.workflow_stato})

    return render(
        request,
        "projects/commessa_workflow.html",
        {"commessa": commessa, "form": form},
    )


# =========================================================
# TEAMWORK — spazio operativo della commessa, organizzato per fase
#
# A differenza delle altre view di questo file (tutte riservate ad
# Admin), il Teamwork è accessibile a chiunque appartenga alla
# commessa: Admin, PM e Consulenti con assegnazione attiva (specifica
# funzionale Teamwork Teamwork). Non introduce un nuovo modello: aggrega
# solo dati già esposti da planning/tasks/phases/documents.
# =========================================================


@login_required
def commessa_teamwork(request, pk):
    commessa = get_object_or_404(
        Commessa.objects.select_related("cliente"),
        pk=pk,
    )

    e_membro = Assegnazione.objects.filter(
        consulente=request.user,
        commessa=commessa,
        stato=Assegnazione.Stato.ATTIVA,
    ).exists()

    gestore = can_manage_commessa(request.user, commessa)
    accesso_portafoglio = can_view_teamwork_without_assignment(request.user)
    accesso_portafoglio_sola_lettura = bool(
        accesso_portafoglio and not gestore and not e_membro
    )

    if not gestore and not e_membro and not accesso_portafoglio:
        raise PermissionDenied(
            "Non appartieni al Teamwork di questa commessa."
        )

    from apps.documents.selectors import visible_documents_for_user
    from apps.phases.models import FaseCommessa
    from apps.tasks.models import Task

    # Conteggio documenti ristretto a quelli che l'utente può davvero
    # vedere: un documento privato non deve comparire nel totale del
    # Teamwork per chi non può aprirlo (solo gli Admin LEF lo vedono).
    documenti_visibili = visible_documents_for_user(request.user)

    from apps.projects.permissions import is_active_pm

    pm_sulla_commessa = is_active_pm(request.user, commessa)

    fasi_queryset = FaseCommessa.objects.filter(commessa=commessa)

    if not gestore and not pm_sulla_commessa and not accesso_portafoglio:
        fasi_queryset = fasi_queryset.filter(
            pk__in=Assegnazione.objects.filter(
                consulente=request.user,
                commessa=commessa,
                stato=Assegnazione.Stato.ATTIVA,
            ).values_list("fase_id", flat=True)
        )

    fasi = list(
        fasi_queryset
        .prefetch_related("assegnazioni__consulente")
        .order_by("ordine", "nome")
    )

    fase_ids = [fase.pk for fase in fasi]

    for fase in fasi:
        fase.task_aperti = Task.objects.filter(
            fase=fase
        ).exclude(
            stato=Task.Stato.COMPLETATA
        ).count()
        fase.documenti_totali = documenti_visibili.filter(
            fase=fase
        ).count()
        fase.membri = list(
            fase.assegnazioni.filter(stato=Assegnazione.Stato.ATTIVA)
            .select_related("consulente")
            .order_by("-ruolo_commessa", "consulente__last_name")
        )

    membri = (
        Assegnazione.objects
        .filter(
            commessa=commessa,
            stato=Assegnazione.Stato.ATTIVA,
            fase_id__in=fase_ids,
        )
        .select_related("consulente", "fase")
        .order_by(
            "fase__ordine",
            "fase__nome",
            "-ruolo_commessa",
            "consulente__last_name",
        )
    )

    task_aperti = Task.objects.filter(
        fase_id__in=fase_ids
    ).exclude(
        stato=Task.Stato.COMPLETATA
    ).count()

    fasi_totali = len(fasi)

    documenti_totali = (
        documenti_visibili.filter(
            commessa=commessa,
        )
        .filter(Q(fase_id__in=fase_ids) | Q(fase__isnull=True))
        .count()
    )

    return render(
        request,
        "projects/commessa_teamwork.html",
        {
            "commessa": commessa,
            "membri": membri,
            "fasi": fasi,
            "task_aperti": task_aperti,
            "fasi_totali": fasi_totali,
            "documenti_totali": documenti_totali,
            "agenda_progress": agenda_progress(commessa),
            "puo_gestire_handover": gestore or pm_sulla_commessa,
            "puo_gestire_workflow": gestore or pm_sulla_commessa,
            "puo_gestire_team": gestore,
            "accesso_portafoglio": accesso_portafoglio_sola_lettura,
            "puo_vedere_pianificazione": not accesso_portafoglio_sola_lettura,
            "puo_vedere_attivita": (
                not accesso_portafoglio_sola_lettura
                or can_view_tasks_portfolio(request.user)
            ),
        },
    )
