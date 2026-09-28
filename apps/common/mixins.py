from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied

from apps.accounts.access import (
    can_view_operational_details,
    can_manage_clients,
    can_manage_projects,
    can_view_audit,
    can_view_executive_dashboard,
    can_view_finance_ledger,
    can_manage_finance,
    can_view_people,
    can_view_portfolio,
    can_view_reports,
    can_view_skill_matrix,
)


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Reindirizza al login gli anonimi e limita le pagine agli Admin LEF."""

    def test_func(self) -> bool:
        user = self.request.user
        return bool(user.is_authenticated and getattr(user, "is_admin_lef", False))

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("Questa pagina è riservata agli Admin LEF.")
        return super().handle_no_permission()


class _PolicyRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    policy = staticmethod(lambda user: False)
    denied_message = "Non hai i permessi per accedere a questa pagina."

    def test_func(self) -> bool:
        return bool(self.policy(self.request.user))

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(self.denied_message)
        return super().handle_no_permission()


class PortfolioReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_portfolio)
    denied_message = "Questa sezione è riservata ai profili di portafoglio autorizzati."


class ClientManagementRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_manage_clients)
    denied_message = "La gestione clienti è riservata ad Admin LEF e Commerciale."


class ProjectManagementRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_manage_projects)
    denied_message = "La gestione anagrafica delle commesse è riservata ad Admin LEF e Commerciale."


class ExecutiveDashboardRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_executive_dashboard)
    denied_message = "La dashboard direzionale non è disponibile per questo profilo."


class ReportsReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_reports)
    denied_message = "Non hai accesso ai report direzionali."


class FinanceReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_finance_ledger)
    denied_message = "Questa sezione è riservata ad Admin LEF e Amministrazione."


class FinanceManagementRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_manage_finance)
    denied_message = "La gestione amministrativa è riservata ad Admin LEF e Amministrazione."


class TimesheetReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(
        lambda user: can_view_operational_details(user) or can_view_finance_ledger(user)
    )
    denied_message = "Non hai accesso ai dati di ore e spese."


class AuditReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_audit)
    denied_message = "Non hai accesso al registro audit."


class PeopleReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_people)
    denied_message = "Non hai accesso a Persone e ruoli."


class SkillMatrixReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_skill_matrix)
    denied_message = "Non hai accesso alla Skill Matrix."


class OperationalRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_operational_details)
    denied_message = "Questa sezione è riservata ai profili operativi."
