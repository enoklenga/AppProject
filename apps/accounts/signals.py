"""Invalidazione della cache del perimetro Business Unit.

Ogni modifica a BU, appartenenze o ruoli incrementa la versione globale del
perimetro: le istanze utente già caricate ricalcolano le BU gestite alla
prossima verifica dei permessi.
"""
from django.db.models.signals import post_delete, post_save

from .access import invalidate_scope_cache
from .models import BusinessUnit, User, UserBusinessUnit


def connect_scope_signals() -> None:
    for model in (BusinessUnit, UserBusinessUnit, User):
        post_save.connect(
            invalidate_scope_cache,
            sender=model,
            dispatch_uid=f"lef_bu_scope_save_{model.__name__}",
        )
        post_delete.connect(
            invalidate_scope_cache,
            sender=model,
            dispatch_uid=f"lef_bu_scope_delete_{model.__name__}",
        )
