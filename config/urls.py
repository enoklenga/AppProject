import logging

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView

from apps.accounts.auth_views import (
    NokihubLoginView,
    NokihubActivationConfirmView,
    NokihubPasswordChangeView,
    NokihubPasswordResetConfirmView,
)
from apps.accounts.forms import NokihubAuthenticationForm
from apps.common.views import home

logger = logging.getLogger("lef.health")


def _health_response(payload, *, status=200):
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store"
    return response


def health(request):
    return _health_response(
        {
            "status": "ok",
            "service": "lef-timesheet",
            "check": "liveness",
        }
    )


def health_ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        # Il dettaglio tecnico resta nei log server-side e non viene esposto
        # pubblicamente dall'endpoint di readiness.
        logger.exception("Readiness database check failed")
        return _health_response(
            {
                "status": "error",
                "service": "lef-timesheet",
                "check": "readiness",
                "database": "unavailable",
            },
            status=503,
        )

    return _health_response(
        {
            "status": "ok",
            "service": "lef-timesheet",
            "check": "readiness",
            "database": "available",
        }
    )


urlpatterns = [
    path("", home, name="home"),
    path("health/", health, name="health"),
    path("health/ready/", health_ready, name="health_ready"),
    path("admin/", admin.site.urls),
    path(
        "login/",
        NokihubLoginView.as_view(
            template_name="registration/login.html",
            authentication_form=NokihubAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "account/attiva/<uidb64>/<token>/",
        NokihubActivationConfirmView.as_view(
            template_name="registration/account_activation_confirm.html",
            success_url="/account/attivazione/completata/",
        ),
        name="account_activation_confirm",
    ),
    path(
        "account/attivazione/completata/",
        TemplateView.as_view(
            template_name="registration/account_activation_complete.html",
        ),
        name="account_activation_complete",
    ),
    path(
        "password/change/",
        NokihubPasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            success_url="/",
        ),
        name="password_change",
    ),
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.txt",
            html_email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url="/password/reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password/reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password/reset/confirm/<uidb64>/<token>/",
        NokihubPasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url="/password/reset/complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
    path("gestione/consulenti/", include("apps.accounts.urls")),
    path("gestione/", include("apps.projects.urls")),
    path("timesheet/", include("apps.timesheets.urls")),
    path(
        "pianificazione/",
        include("apps.planning.urls"),
    ),
    path(
        "attivita/",
        include("apps.tasks.urls"),
    ),
    path(
        "notifiche/",
        include("apps.notifications.urls"),
    ),
    path(
        "documenti/",
        include("apps.documents.urls"),
    ),
    path(
        "fasi/",
        include("apps.phases.urls"),
    ),
    
    path("controllo/", include("apps.operations.urls")),
    path("api/v1/", include("apps.api.urls")),
    
]
