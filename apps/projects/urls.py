from django.urls import path

from .views import (
    AssegnazioneCreateView,
    AssegnazioneListView,
    AssegnazioneToggleStateView,
    AssegnazioneUpdateView,
    ClienteCreateView,
    ClienteListView,
    ClienteToggleActiveView,
    ClienteUpdateView,
    CommessaCreateView,
    CommessaListView,
    CommessaToggleStateView,
    CommessaUpdateView,
    FasiPerCommessaView,
    TariffaCreateView,
    TariffaListView,
    commessa_handover,
    commessa_teamwork,
    commessa_workflow,
)

app_name = "projects"

urlpatterns = [
    path("clienti/", ClienteListView.as_view(), name="cliente-list"),
    path("clienti/nuovo/", ClienteCreateView.as_view(), name="cliente-create"),
    path(
        "clienti/<uuid:pk>/modifica/",
        ClienteUpdateView.as_view(),
        name="cliente-update",
    ),
    path(
        "clienti/<uuid:pk>/cambia-stato/",
        ClienteToggleActiveView.as_view(),
        name="cliente-toggle-active",
    ),

    path("commesse/", CommessaListView.as_view(), name="commessa-list"),
    path("commesse/nuova/", CommessaCreateView.as_view(), name="commessa-create"),
    path(
        "commesse/<uuid:pk>/modifica/",
        CommessaUpdateView.as_view(),
        name="commessa-update",
    ),
    path(
        "commesse/<uuid:pk>/cambia-stato/",
        CommessaToggleStateView.as_view(),
        name="commessa-toggle-state",
    ),
    path(
        "commesse/<uuid:pk>/handover/",
        commessa_handover,
        name="commessa-handover",
    ),
    path(
        "commesse/<uuid:pk>/workflow/",
        commessa_workflow,
        name="commessa-workflow",
    ),
    path(
        "commesse/<uuid:pk>/teamwork/",
        commessa_teamwork,
        name="commessa-teamwork",
    ),

    path(
        "assegnazioni/",
        AssegnazioneListView.as_view(),
        name="assegnazione-list",
    ),
    path(
        "assegnazioni/nuova/",
        AssegnazioneCreateView.as_view(),
        name="assegnazione-create",
    ),
    path(
        "assegnazioni/<uuid:pk>/modifica/",
        AssegnazioneUpdateView.as_view(),
        name="assegnazione-update",
    ),
    path(
        "assegnazioni/<uuid:pk>/cambia-stato/",
        AssegnazioneToggleStateView.as_view(),
        name="assegnazione-toggle-state",
    ),

    path(
        "tariffe/",
        TariffaListView.as_view(),
        name="tariffa-list",
    ),
    path(
        "tariffe/nuova/",
        TariffaCreateView.as_view(),
        name="tariffa-create",
    ),

    path(
        "ajax/fasi-per-commessa/",
        FasiPerCommessaView.as_view(),
        name="fasi-per-commessa",
    ),
]