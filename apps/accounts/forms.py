from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Skill, User, UserSkill


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
        if self.instance.pk and ruolo not in ruoli_ingaggiabili:
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
            self.instance.pk
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
