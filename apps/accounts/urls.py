from django.urls import path

from .views import (
    ConsulenteCreateView,
    ConsulenteListView,
    ConsulenteResendInviteView,
    ConsulenteToggleActiveView,
    ConsulenteUpdateView,
    SkillCreateView,
    SkillListView,
    SkillMatrixUserUpdateView,
    SkillMatrixView,
    SkillUpdateView,
)

app_name = "accounts"

urlpatterns = [
    path("", ConsulenteListView.as_view(), name="consulente-list"),
    path("nuovo/", ConsulenteCreateView.as_view(), name="consulente-create"),
    path(
        "<uuid:pk>/modifica/",
        ConsulenteUpdateView.as_view(),
        name="consulente-update",
    ),
    path(
        "<uuid:pk>/cambia-stato/",
        ConsulenteToggleActiveView.as_view(),
        name="consulente-toggle-active",
    ),
    path(
        "<uuid:pk>/reinvia-invito/",
        ConsulenteResendInviteView.as_view(),
        name="consulente-resend-invite",
    ),
    path("skill/", SkillListView.as_view(), name="skill-list"),
    path("skill/nuova/", SkillCreateView.as_view(), name="skill-create"),
    path("skill/<uuid:pk>/modifica/", SkillUpdateView.as_view(), name="skill-update"),
    path("skill-matrix/", SkillMatrixView.as_view(), name="skill-matrix"),
    path(
        "skill-matrix/<uuid:pk>/",
        SkillMatrixUserUpdateView.as_view(),
        name="skill-matrix-user-update",
    ),
]
