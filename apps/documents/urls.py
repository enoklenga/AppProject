from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path(
        "",
        views.document_list,
        name="document-list",
    ),
    path(
        "carica/",
        views.document_upload,
        name="document-upload",
    ),
    path(
        "fasi/",
        views.document_phases,
        name="document-phases",
    ),
    path(
        "<uuid:pk>/scarica/",
        views.document_download,
        name="document-download",
    ),
    path(
        "<uuid:pk>/elimina/",
        views.document_delete,
        name="document-delete",
    ),
]
