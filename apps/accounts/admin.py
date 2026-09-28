from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Skill, User, UserSkill


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = (
        "email",
        "first_name",
        "last_name",
        "ruolo",
        "is_active",
        "is_staff",
    )
    list_filter = ("ruolo", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Anagrafica",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "telefono",
                    "ruolo",
                    "deve_cambiare_password",
                )
            },
        ),
        (
            "Permessi",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Date", {"fields": ("last_login", "date_joined")}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and "is_active" not in readonly:
            readonly.append("is_active")
        return tuple(readonly)

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "ruolo",
                    "is_active",
                    "is_staff",
                ),
            },
        ),
    )


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("nome", "categoria", "attiva")
    list_filter = ("attiva", "categoria")
    search_fields = ("nome", "categoria", "descrizione")


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ("utente", "skill", "livello")
    list_filter = ("livello", "skill")
    search_fields = (
        "utente__email",
        "utente__first_name",
        "utente__last_name",
        "skill__nome",
    )
