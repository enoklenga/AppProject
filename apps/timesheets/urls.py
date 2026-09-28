from django.urls import path

from .views import (
    RigaOreApprovaView,
    RigaOreCreateView,
    RigaOreDeleteView,
    RigaOreListView,
    RigaOreRifiutaView,
    RigaOreUpdateView,
    SpesaApprovaView,
    SpesaCreateView,
    SpesaDeleteView,
    SpesaListView,
    SpesaRifiutaView,
    SpesaUpdateView,
)

app_name = "timesheets"

urlpatterns = [
    path("ore/", RigaOreListView.as_view(), name="ore-list"),
    path("ore/nuova/", RigaOreCreateView.as_view(), name="ore-create"),
    path(
        "ore/<uuid:pk>/modifica/",
        RigaOreUpdateView.as_view(),
        name="ore-update",
    ),
    path(
        "ore/<uuid:pk>/elimina/",
        RigaOreDeleteView.as_view(),
        name="ore-delete",
    ),
    path(
        "ore/<uuid:pk>/approva/",
        RigaOreApprovaView.as_view(),
        name="ore-approva",
    ),
    path(
        "ore/<uuid:pk>/rifiuta/",
        RigaOreRifiutaView.as_view(),
        name="ore-rifiuta",
    ),
    path("spese/", SpesaListView.as_view(), name="spesa-list"),
    path(
        "spese/nuova/",
        SpesaCreateView.as_view(),
        name="spesa-create",
    ),
    path(
        "spese/<uuid:pk>/modifica/",
        SpesaUpdateView.as_view(),
        name="spesa-update",
    ),
    path(
        "spese/<uuid:pk>/elimina/",
        SpesaDeleteView.as_view(),
        name="spesa-delete",
    ),
    path(
        "spese/<uuid:pk>/approva/",
        SpesaApprovaView.as_view(),
        name="spesa-approva",
    ),
    path(
        "spese/<uuid:pk>/rifiuta/",
        SpesaRifiutaView.as_view(),
        name="spesa-rifiuta",
    ),
]
