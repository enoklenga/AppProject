"""Widget HTML5 condivisi.

Un ``<input type="date">`` accetta SOLO valori ISO (AAAA-MM-GG). Con
``LANGUAGE_CODE = "it-it"`` Django renderizza di default le date nel formato
locale (GG/MM/AAAA): il browser le scarta e il campo appare vuoto nei form di
modifica. Al salvataggio la data veniva quindi persa (campi facoltativi
azzerati) oppure rifiutata come "obbligatoria".

Tutti i form devono usare questi widget per le date.
"""
from django import forms


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None, format=None):
        super().__init__(attrs=attrs, format=format or "%Y-%m-%d")


class MonthInput(forms.DateInput):
    input_type = "month"

    def __init__(self, attrs=None, format=None):
        super().__init__(attrs=attrs, format=format or "%Y-%m")
