from django.urls import path

from . import views


app_name = "planning"


urlpatterns = [
    path(
        "",
        views.pianificazione_list,
        name="pianificazione-list",
    ),
    path(
        "nuova/",
        views.pianificazione_create,
        name="pianificazione-create",
    ),
    path(
        "<uuid:pk>/modifica/",
        views.pianificazione_update,
        name="pianificazione-update",
    ),
    path(
        "<uuid:pk>/conferma/",
        views.pianificazione_confirm,
        name="pianificazione-confirm",
    ),
    path(
        "<uuid:pk>/elimina/",
        views.pianificazione_delete,
        name="pianificazione-delete",
    ),
]