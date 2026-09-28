"""Regressione: i campi <input type="date"> devono ricevere valori ISO.

Con LANGUAGE_CODE="it-it" Django formatta le date come GG/MM/AAAA; il browser
le scarta e, salvando un form di modifica, la data andava persa.
"""
from datetime import date

from django import forms
from django.test import SimpleTestCase

from apps.common.widgets import DateInput, MonthInput
from apps.operations.forms import AuditLogFilterForm, PeriodoFiltroForm
from apps.phases.forms import FaseForm
from apps.planning.forms import PianificazioneForm
from apps.projects.forms import AssegnazioneForm, CommessaForm, TariffaAssegnazioneForm
from apps.tasks.forms import TaskForm
from apps.timesheets.forms import RigaOreForm, SpesaTrasfertaForm


class DateWidgetTests(SimpleTestCase):
    def test_shared_widgets_render_iso_values(self):
        self.assertIn('value="2026-09-23"', DateInput().render("d", date(2026, 9, 23)))
        self.assertIn('value="2026-09"', MonthInput().render("m", date(2026, 9, 1)))

    def test_every_form_date_field_uses_iso_widget(self):
        form_classes = [
            CommessaForm, AssegnazioneForm, TariffaAssegnazioneForm, RigaOreForm,
            SpesaTrasfertaForm, TaskForm, FaseForm, PianificazioneForm,
            PeriodoFiltroForm, AuditLogFilterForm,
        ]
        for form_class in form_classes:
            for name, field in form_class.base_fields.items():
                if isinstance(field, forms.DateField) and field.widget.input_type in ("date", "month"):
                    with self.subTest(form=form_class.__name__, field=name):
                        self.assertIsInstance(field.widget, (DateInput, MonthInput))
