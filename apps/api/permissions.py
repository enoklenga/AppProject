from rest_framework.permissions import BasePermission

from apps.accounts.access import is_global_manager, is_platform_admin


class IsAdminLEF(BasePermission):
    """Funzioni di *piattaforma* (es. token API): solo Admin LEF."""

    message = "Questa funzione è riservata agli Admin LEF."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and is_platform_admin(request.user))


class IsGlobalManager(BasePermission):
    """Back office aziendale: Admin LEF e Amministrazione.

    Il Responsabile BU usa le stesse funzioni dall'interfaccia web, dove i
    dati sono filtrati sulla propria Business Unit.
    """

    message = "Questa funzione è riservata ad Admin LEF e Amministrazione."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and is_global_manager(request.user))


class IsProjectManager(BasePermission):
    message = "Questa funzione è riservata ai Project Manager."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if is_global_manager(request.user):
            return False

        from apps.api.querysets import commesse_gestite_ids

        return commesse_gestite_ids(request.user).exists()
