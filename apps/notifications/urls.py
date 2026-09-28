from django.urls import path

from . import views


app_name = "notifications"

urlpatterns = [
    # =====================================================
    # ELENCO
    # =====================================================

    path(
        "",
        views.notification_list,
        name="notification-list",
    ),

    # =====================================================
    # AZIONI GENERALI
    # =====================================================

    path(
        "tutte-lette/",
        views.notification_mark_all_read,
        name="notification-mark-all-read",
    ),

    # =====================================================
    # SINGOLA NOTIFICA
    # =====================================================

    path(
        "<uuid:pk>/apri/",
        views.notification_open,
        name="notification-open",
    ),

    path(
        "<uuid:pk>/letta/",
        views.notification_mark_read,
        name="notification-mark-read",
    ),

    path(
        "<uuid:pk>/non-letta/",
        views.notification_mark_unread,
        name="notification-mark-unread",
    ),

    path(
        "preferenze/",
        views.notification_preferences,
        name="preferences",
    ),
]


