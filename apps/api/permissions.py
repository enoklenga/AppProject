from rest_framework.permissions import BasePermission


class IsAdminLEF(BasePermission):
    message = "Questa funzione è riservata agli Admin LEF."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_admin_lef", False)
        )



class IsProjectManager(BasePermission):
    message = "Questa funzione è riservata ai Project Manager."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, "is_admin_lef", False):
            return False

        from apps.api.querysets import commesse_gestite_ids

        return commesse_gestite_ids(request.user).exists()
