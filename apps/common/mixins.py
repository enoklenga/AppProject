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
    can_view_reference_portfolio,
    can_view_assignments_register,
    can_use_backoffice_control,
    can_view_reports,
    can_view_skill_matrix,
    can_view_business_units,
    can_edit_business_units,
    can_manage_skill_catalog,
    can_manage_assignments,
    is_manager,
    is_platform_admin,
)


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Pagine di *piattaforma* riservate all'Admin LEF (account e ruoli)."""

    def test_func(self) -> bool:
        return is_platform_admin(self.request.user)

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


class ReferencePortfolioReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_reference_portfolio)
    denied_message = "Non hai accesso alle anagrafiche di portafoglio."


class AssignmentsRegisterReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_assignments_register)
    denied_message = "Non hai accesso al registro assegnazioni."


class BackofficeControlRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_use_backoffice_control)
    denied_message = "Questa funzione è riservata ad Admin LEF e Amministrazione."


class ManagementRequiredMixin(_PolicyRequiredMixin):
    """Interfaccia di gestione: Admin, Amministrazione e Responsabili BU.

    Il perimetro (tutto o solo la propria BU) va poi applicato ai queryset con
    ``commesse_in_scope`` / ``persone_in_scope``.
    """

    policy = staticmethod(is_manager)
    denied_message = "Questa sezione è riservata alla gestione (Admin, Amministrazione, Responsabili BU)."


class AssignmentsManagementRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_manage_assignments)
    denied_message = "La gestione delle assegnazioni è riservata ad Admin, Amministrazione e Responsabili BU."


class BusinessUnitReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_business_units)
    denied_message = "Non hai accesso alle Business Unit."


class BusinessUnitEditRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_edit_business_units)
    denied_message = "L'anagrafica delle Business Unit è gestita da Admin e Amministrazione."


class SkillCatalogRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_manage_skill_catalog)
    denied_message = "Il catalogo skill è gestito da Admin e Amministrazione."


class ClientManagementRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_manage_clients)
    denied_message = "La gestione clienti è riservata a gestione (Admin, Amministrazione, Responsabili BU) e Commerciale."


class ProjectManagementRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_manage_projects)
    denied_message = "La gestione delle commesse è riservata a gestione (Admin, Amministrazione, Responsabili BU) e Commerciale."


class ExecutiveDashboardRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_executive_dashboard)
    denied_message = "La dashboard direzionale non è disponibile per questo profilo."


class ReportsReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_reports)
    denied_message = "Non hai accesso ai report direzionali."


class FinanceReadRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_view_finance_ledger)
    denied_message = "Questa sezione è riservata ad Admin, Amministrazione e Responsabili BU."


class FinanceManagementRequiredMixin(_PolicyRequiredMixin):
    policy = staticmethod(can_manage_finance)
    denied_message = "La gestione amministrativa è riservata ad Admin, Amministrazione e Responsabili BU."


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
