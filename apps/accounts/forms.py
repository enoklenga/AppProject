from django import forms
from django.db.models import Q

from apps.common.widgets import DateInput
from django.contrib.auth.forms import AuthenticationForm

from .models import BusinessUnit, Skill, User, UserBusinessUnit, UserSkill


class NokihubAuthenticationForm(AuthenticationForm):
    """AuthenticationForm di default, con placeholder/tipo campo custom."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "nome@azienda.it",
                "autocomplete": "email",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Inserisci la tua password",
                "autocomplete": "current-password",
            }
        ),
    )


class _RuoloUtenteMixin:
    def _configure_role_field(self):
        # Tutti i ruoli applicativi, incluso Admin LEF, sono gestibili da
        # Persone e ruoli. Il superuser Django resta un bootstrap tecnico
        # separato e non viene creato da questo form.
        self.fields["ruolo"].choices = list(User.Ruolo.choices)
        self.fields["ruolo"].help_text = (
            "Il ruolo Project Manager non si assegna qui: viene attribuito "
            "sulla singola commessa tramite Assegnazioni."
        )


class ConsulenteCreateForm(_RuoloUtenteMixin, forms.ModelForm):
    """Creazione utente tramite invito, senza password scelta dall'Admin."""

    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "telefono",
            "ruolo",
        )
        labels = {
            "first_name": "Nome",
            "last_name": "Cognome",
            "ruolo": "Ruolo organizzativo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_role_field()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = None
        user.is_active = False
        user.deve_cambiare_password = True
        user.set_unusable_password()
        if commit:
            user.save()
        return user


class ConsulenteUpdateForm(_RuoloUtenteMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "telefono",
            "ruolo",
            "deve_cambiare_password",
        )
        labels = {
            "first_name": "Nome",
            "last_name": "Cognome",
            "ruolo": "Ruolo organizzativo",
            "deve_cambiare_password": "Cambio password richiesto",
        }

    def __init__(self, *args, attore=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.attore = attore
        self._configure_role_field()

    def clean_ruolo(self):
        ruolo = self.cleaned_data["ruolo"]
        ruoli_ingaggiabili = {
            User.Ruolo.CONSULENTE,
            User.Ruolo.RESPONSABILE_CONSULENZA,
        }
        if not self.instance._state.adding and ruolo not in ruoli_ingaggiabili:
            from apps.projects.models import Assegnazione

            if Assegnazione.objects.filter(
                consulente=self.instance,
                stato=Assegnazione.Stato.ATTIVA,
            ).exists():
                raise forms.ValidationError(
                    "Concludi prima le assegnazioni attive: un utente con ruolo "
                    "non operativo non può restare ingaggiato su una commessa."
                )

        # Un Admin non può auto-retrocedersi: la modifica deve essere fatta
        # da un altro Admin, così la sessione corrente non perde i privilegi
        # nel mezzo dell'operazione. Inoltre va sempre preservato almeno un
        # Admin attivo nel sistema.
        if (
            not self.instance._state.adding
            and self.instance.ruolo == User.Ruolo.ADMIN
            and ruolo != User.Ruolo.ADMIN
        ):
            if self.attore and self.attore.pk == self.instance.pk:
                raise forms.ValidationError(
                    "Non puoi modificare il tuo ruolo Admin. Usa un altro Admin LEF."
                )
            if self.instance.is_active:
                altri_admin_attivi = User.objects.filter(
                    ruolo=User.Ruolo.ADMIN,
                    is_active=True,
                ).exclude(pk=self.instance.pk)
                if not altri_admin_attivi.exists():
                    raise forms.ValidationError(
                        "Deve rimanere almeno un Admin LEF attivo nel sistema."
                    )
        if (
            not self.instance._state.adding
            and self.instance.ruolo == User.Ruolo.RESPONSABILE_CONSULENZA
            and ruolo != User.Ruolo.RESPONSABILE_CONSULENZA
        ):
            from .access import membership_current_q

            if UserBusinessUnit.objects.filter(
                membership_current_q(),
                utente=self.instance,
                responsabile=True,
                business_unit__attiva=True,
            ).exists():
                raise forms.ValidationError(
                    "Revoca prima le responsabilità attive sulle Business Unit: "
                    "il cambio di ruolo non può lasciare deleghe organizzative sospese."
                )
        return ruolo


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ("nome", "categoria", "descrizione", "attiva")
        labels = {
            "nome": "Skill",
            "categoria": "Dimensione / categoria",
            "descrizione": "Descrizione",
            "attiva": "Skill attiva",
        }
        widgets = {
            "descrizione": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_nome(self):
        return self.cleaned_data["nome"].strip()

    def clean_categoria(self):
        return self.cleaned_data["categoria"].strip()


class SkillMatrixUserForm(forms.Form):
    """Form dinamico per impostare i tre livelli della matrice di una risorsa."""

    def __init__(self, *args, utente: User, **kwargs):
        super().__init__(*args, **kwargs)
        self.utente = utente
        skills = list(Skill.objects.filter(attiva=True).order_by("categoria", "nome"))
        correnti = {
            voce.skill_id: voce.livello
            for voce in UserSkill.objects.filter(utente=utente, skill__in=skills)
        }

        for skill in skills:
            label = skill.nome
            if skill.categoria:
                label = f"{skill.categoria} · {skill.nome}"
            self.fields[f"skill_{skill.pk}"] = forms.TypedChoiceField(
                label=label,
                choices=[("", "Non valorizzata"), *UserSkill.Livello.choices],
                coerce=lambda value: int(value) if value not in (None, "") else None,
                empty_value=None,
                required=False,
                initial=correnti.get(skill.pk),
            )
            if skill.descrizione:
                self.fields[f"skill_{skill.pk}"].help_text = skill.descrizione

    def save(self):
        skills = {str(skill.pk): skill for skill in Skill.objects.filter(attiva=True)}
        for field_name, livello in self.cleaned_data.items():
            if not field_name.startswith("skill_"):
                continue
            skill_id = field_name.removeprefix("skill_")
            skill = skills.get(skill_id)
            if skill is None:
                continue
            if livello is None:
                UserSkill.objects.filter(utente=self.utente, skill=skill).delete()
            else:
                UserSkill.objects.update_or_create(
                    utente=self.utente,
                    skill=skill,
                    defaults={"livello": livello},
                )


class UserProfileForm(forms.ModelForm):
    """Dati che ogni utente può modificare autonomamente sul proprio profilo."""

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "telefono",
            "foto_profilo",
        )
        labels = {
            "first_name": "Nome",
            "last_name": "Cognome",
            "telefono": "Telefono",
            "foto_profilo": "Foto profilo",
        }
        widgets = {
            "foto_profilo": forms.ClearableFileInput(
                attrs={
                    "accept": "image/jpeg,image/png,image/webp",
                }
            )
        }


class BusinessUnitForm(forms.ModelForm):
    class Meta:
        model = BusinessUnit
        fields = ("nome", "codice", "descrizione", "attiva")
        labels = {
            "nome": "Business Unit",
            "codice": "Codice",
            "descrizione": "Descrizione",
            "attiva": "Business Unit attiva",
        }
        widgets = {"descrizione": forms.Textarea(attrs={"rows": 3})}

    def clean_nome(self):
        return self.cleaned_data["nome"].strip()

    def clean_codice(self):
        return self.cleaned_data["codice"].strip().upper()


class UserBusinessUnitForm(forms.ModelForm):
    class Meta:
        model = UserBusinessUnit
        fields = (
            "utente",
            "business_unit",
            "responsabile",
            "puo_essere_pm",
            "attiva",
            "data_inizio",
            "data_fine",
        )
        labels = {
            "utente": "Persona",
            "business_unit": "Business Unit",
            "responsabile": "Responsabile della Business Unit",
            "puo_essere_pm": "Abilitato come Project Manager",
            "attiva": "Appartenenza attiva",
            "data_inizio": "Data inizio",
            "data_fine": "Data fine",
        }

        widgets = {
            "data_inizio": DateInput(),
            "data_fine": DateInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .access import can_designate_bu_managers, is_global_manager, managed_business_unit_ids

        self.user = user
        current_user_id = getattr(self.instance, "utente_id", None)
        current_bu_id = getattr(self.instance, "business_unit_id", None)
        utenti = User.objects.filter(Q(is_active=True) | Q(pk=current_user_id))
        business_units = BusinessUnit.objects.filter(Q(attiva=True) | Q(pk=current_bu_id))
        if user is not None and not is_global_manager(user):
            # Responsabile BU: compone il team della propria BU con risorse operative.
            utenti = utenti.filter(
                ruolo__in=(User.Ruolo.CONSULENTE, User.Ruolo.RESPONSABILE_CONSULENZA)
            )
            business_units = business_units.filter(pk__in=managed_business_unit_ids(user))
            self.fields["business_unit"].empty_label = None
        self.fields["utente"].queryset = utenti.order_by("last_name", "first_name", "email")
        self.fields["business_unit"].queryset = business_units.order_by("nome")
        self.fields["responsabile"].help_text = (
            "Conferisce il governo della BU (interfaccia di gestione limitata alla BU). "
            "Richiede il ruolo 'Responsabile Business Unit'; non rende automaticamente "
            "PM di tutte le commesse."
        )
        self.fields["puo_essere_pm"].help_text = (
            "Consente alla persona di essere nominata PM sulle commesse di questa BU."
        )
        # Nominare un Responsabile concede poteri di gestione: è una funzione
        # di piattaforma riservata all'Admin LEF.
        if user is not None and not can_designate_bu_managers(user):
            self.fields["responsabile"].disabled = True
            self.fields["responsabile"].help_text = (
                "La nomina del Responsabile della Business Unit è gestita dall'Admin LEF."
            )

    def clean(self):
        cleaned = super().clean()
        utente = cleaned.get("utente")
        if cleaned.get("responsabile") and utente is not None:
            if utente.ruolo != User.Ruolo.RESPONSABILE_CONSULENZA:
                self.add_error(
                    "responsabile",
                    "Per nominarla Responsabile, la persona deve avere il ruolo "
                    "'Responsabile Business Unit' (Persone e ruoli).",
                )
        return cleaned
