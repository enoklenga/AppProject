from django.urls import path

from .views import (
    BusinessUnitCreateView,
    BusinessUnitDetailView,
    BusinessUnitListView,
    BusinessUnitUpdateView,
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
    UserBusinessUnitCreateView,
    UserBusinessUnitListView,
    UserBusinessUnitUpdateView,
    UserProfileUpdateView,
)

app_name = "accounts"

urlpatterns = [
    path("business-unit/", BusinessUnitListView.as_view(), name="business-unit-list"),
    path("business-unit/nuova/", BusinessUnitCreateView.as_view(), name="business-unit-create"),
    path("business-unit/<uuid:pk>/", BusinessUnitDetailView.as_view(), name="business-unit-detail"),
    path("business-unit/<uuid:pk>/modifica/", BusinessUnitUpdateView.as_view(), name="business-unit-update"),
    path("business-unit/appartenenze/", UserBusinessUnitListView.as_view(), name="user-business-unit-list"),
    path("business-unit/appartenenze/nuova/", UserBusinessUnitCreateView.as_view(), name="user-business-unit-create"),
    path("business-unit/appartenenze/<uuid:pk>/modifica/", UserBusinessUnitUpdateView.as_view(), name="user-business-unit-update"),
    path("profilo/", UserProfileUpdateView.as_view(), name="profile"),
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
