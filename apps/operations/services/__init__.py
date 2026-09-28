"""
Punto d'ingresso unico per la logica di apps.operations.

Diviso in tre moduli per responsabilità (vedi ARCHITECTURE.md):
    periodi.py      chiusura/riapertura periodo, valorizzazione economica
    dashboard.py     dashboard Admin e Project Manager
    promemoria.py    promemoria automatici via email

Questo file ri-espone tutti i nomi pubblici così come venivano importati
prima della divisione: il resto del progetto continua a scrivere
    from apps.operations.services import chiudi_periodo, dashboard_admin
esattamente come prima.
"""
from .periodi import (
    RigaValorizzata,
    RiepilogoPeriodo,
    tariffa_vigente,
    valorizza_periodo,
    righe_senza_tariffa,
    chiudi_periodo,
    riapri_periodo,
)
from .dashboard import (
    AggregatoEconomico,
    AvanzamentoCommessa,
    DashboardAdminData,
    AvanzamentoConsulentePM,
    DashboardPMData,
    dashboard_admin,
    commesse_gestite_da_pm,
    dashboard_pm,
)
from .promemoria import (
    DestinatarioPromemoria,
    EsitoInvioPromemoria,
    estremi_mese,
    configurazione_promemoria_corrente,
    inizializza_configurazione_promemoria,
    consulenti_senza_ore,
    periodo_promemoria_chiuso,
    promemoria_programmato_dovuto,
    invia_promemoria,
    invia_email_test,
)

__all__ = [
    "RigaValorizzata", "RiepilogoPeriodo", "tariffa_vigente", "valorizza_periodo",
    "righe_senza_tariffa", "chiudi_periodo", "riapri_periodo",
    "AggregatoEconomico", "AvanzamentoCommessa", "DashboardAdminData",
    "AvanzamentoConsulentePM", "DashboardPMData", "dashboard_admin",
    "commesse_gestite_da_pm", "dashboard_pm",
    "DestinatarioPromemoria", "EsitoInvioPromemoria", "estremi_mese",
    "configurazione_promemoria_corrente", "inizializza_configurazione_promemoria",
    "consulenti_senza_ore", "periodo_promemoria_chiuso",
    "promemoria_programmato_dovuto", "invia_promemoria", "invia_email_test",
]
