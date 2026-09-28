from django.urls import path

from . import views

app_name = "phases"

urlpatterns = [
    path("", views.fase_list, name="fase-list"),
    path("nuova/", views.fase_create, name="fase-create"),
    path("<uuid:pk>/modifica/", views.fase_update, name="fase-update"),
    path("<uuid:pk>/elimina/", views.fase_delete, name="fase-delete"),
]
