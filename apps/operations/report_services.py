from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from apps.common.export_security import spreadsheet_safe_row
from apps.timesheets.models import RigaOre, SpesaTrasferta
from .services import dashboard_admin, precarica_tariffe, tariffa_vigente


@dataclass(frozen=True)
class FiltriReport:
    anno: int
    mese: int
    cliente_id: Any = None
    commessa_id: Any = None
    consulente_id: Any = None
    fase_id: Any = None
    # None = nessun limite; tupla di id = perimetro Business Unit.
    business_unit_ids: Any = None

    @property
    def mese_testo(self) -> str:
        return f"{self.mese:02d}/{self.anno}"


def _filtra_righe(filtri: FiltriReport):
    queryset = RigaOre.objects.filter(
        data__year=filtri.anno,
        data__month=filtri.mese,
    ).select_related(
        "assegnazione",
        "assegnazione__consulente",
        "assegnazione__commessa",
        "assegnazione__commessa__cliente",
        "assegnazione__fase",
        "inserita_da",
        "ultima_modifica_da",
    )
    if filtri.cliente_id:
        queryset = queryset.filter(
            assegnazione__commessa__cliente_id=filtri.cliente_id
        )
    if filtri.commessa_id:
        queryset = queryset.filter(
            assegnazione__commessa_id=filtri.commessa_id
        )
    if filtri.consulente_id:
        queryset = queryset.filter(assegnazione__consulente_id=filtri.consulente_id)
    if filtri.fase_id:
        queryset = queryset.filter(assegnazione__fase_id=filtri.fase_id)
    if filtri.business_unit_ids is not None:
        queryset = queryset.filter(
            assegnazione__commessa__business_unit_id__in=list(filtri.business_unit_ids)
        )
    return queryset.order_by(
        "data",
        "assegnazione__commessa__codice",
        "assegnazione__consulente__last_name",
        "assegnazione__consulente__first_name",
    )


def _filtra_spese(filtri: FiltriReport):
    queryset = SpesaTrasferta.objects.filter(
        data__year=filtri.anno,
        data__month=filtri.mese,
    ).select_related(
        "assegnazione",
        "assegnazione__consulente",
        "assegnazione__commessa",
        "assegnazione__commessa__cliente",
        "assegnazione__fase",
        "inserita_da",
        "ultima_modifica_da",
    )
    if filtri.cliente_id:
        queryset = queryset.filter(
            assegnazione__commessa__cliente_id=filtri.cliente_id
        )
    if filtri.commessa_id:
        queryset = queryset.filter(
            assegnazione__commessa_id=filtri.commessa_id
        )
    if filtri.consulente_id:
        queryset = queryset.filter(assegnazione__consulente_id=filtri.consulente_id)
    if filtri.fase_id:
        queryset = queryset.filter(assegnazione__fase_id=filtri.fase_id)
    if filtri.business_unit_ids is not None:
        queryset = queryset.filter(
            assegnazione__commessa__business_unit_id__in=list(filtri.business_unit_ids)
        )
    return queryset.order_by(
        "data",
        "assegnazione__commessa__codice",
        "assegnazione__consulente__last_name",
        "assegnazione__consulente__first_name",
    )


def dati_report(filtri: FiltriReport):
    dashboard = dashboard_admin(
        anno=filtri.anno,
        mese=filtri.mese,
        cliente_id=filtri.cliente_id,
        commessa_id=filtri.commessa_id,
        consulente_id=filtri.consulente_id,
        fase_id=filtri.fase_id,
        business_unit_ids=filtri.business_unit_ids,
    )
    return {
        "filtri": filtri,
        "dashboard": dashboard,
        "righe": list(_filtra_righe(filtri)),
        "spese": list(_filtra_spese(filtri)),
    }


def _intestazione(ws, titoli):
    ws.append(titoli)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9E7F3")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _adatta_colonne(ws, massimo=45):
    for indice, colonna in enumerate(ws.columns, start=1):
        lunghezza = max(
            len(str(cella.value or ""))
            for cella in colonna
        )
        ws.column_dimensions[get_column_letter(indice)].width = min(
            max(lunghezza + 2, 10),
            massimo,
        )


def _scrivi_aggregati(ws, aggregati):
    _intestazione(
        ws,
        [
            "Voce",
            "Ore",
            "Valore ore",
            "Spese",
            "Totale",
            "Righe senza tariffa",
        ],
    )
    for voce in aggregati:
        ws.append(
            spreadsheet_safe_row(
                [
                    voce.etichetta,
                    voce.ore,
                    voce.valore_ore,
                    voce.spese,
                    voce.totale,
                    voce.righe_senza_tariffa,
                ]
            )
        )
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=5):
        for cell in row:
            cell.number_format = '#,##0.00 [$€-it-IT]'
    _adatta_colonne(ws)


def crea_report_xlsx(filtri: FiltriReport) -> bytes:
    dati = dati_report(filtri)
    dashboard = dati["dashboard"]
    righe = dati["righe"]
    precarica_tariffe(righe)
    spese = dati["spese"]

    workbook = Workbook()
    riepilogo = workbook.active
    riepilogo.title = "Riepilogo"

    riepilogo.append(["Report mensile LEFTRACK"])
    riepilogo["A1"].font = Font(bold=True, size=16)
    riepilogo.append(["Periodo", filtri.mese_testo])
    riepilogo.append(["Ore", dashboard.totale_ore])
    riepilogo.append(["Valore ore", dashboard.totale_valore_ore])
    riepilogo.append(["Spese", dashboard.totale_spese])
    riepilogo.append(["Totale valorizzato", dashboard.totale_fatturabile])
    riepilogo.append(
        ["Righe senza tariffa", dashboard.numero_righe_senza_tariffa]
    )
    for cell in (riepilogo["B4"], riepilogo["B5"], riepilogo["B6"]):
        cell.number_format = '#,##0.00 [$€-it-IT]'
    _adatta_colonne(riepilogo)

    ws_ore = workbook.create_sheet("Ore")
    _intestazione(
        ws_ore,
        [
            "Data",
            "Cliente",
            "Commessa",
            "Fase",
            "Consulente",
            "Attività",
            "Ore",
            "Tariffa",
            "Importo",
            "Nota",
            "Inserita da",
            "Bloccata",
        ],
    )
    for riga in righe:
        tariffa = tariffa_vigente(riga)
        importo = (
            Decimal(riga.ore) * tariffa.tariffa_oraria
            if tariffa is not None
            else None
        )
        ws_ore.append(
            spreadsheet_safe_row(
                [
                    riga.data,
                    riga.assegnazione.commessa.cliente.ragione_sociale,
                    riga.assegnazione.commessa.codice,
                    riga.assegnazione.fase.nome,
                    str(riga.assegnazione.consulente),
                    riga.get_tipo_attivita_display(),
                    riga.ore,
                    tariffa.tariffa_oraria if tariffa else None,
                    importo,
                    riga.nota,
                    str(riga.inserita_da),
                    "Sì" if riga.bloccata_per_consulente else "No",
                ]
            )
        )
    for row in ws_ore.iter_rows(min_row=2):
        row[0].number_format = "dd/mm/yyyy"
        row[6].number_format = '#,##0.00 [$€-it-IT]'
        row[7].number_format = '#,##0.00 [$€-it-IT]'
    _adatta_colonne(ws_ore)

    ws_spese = workbook.create_sheet("Spese")
    _intestazione(
        ws_spese,
        [
            "Data",
            "Cliente",
            "Commessa",
            "Fase",
            "Consulente",
            "Categoria",
            "Importo",
            "Nota",
            "Inserita da",
            "Bloccata",
        ],
    )
    for spesa in spese:
        ws_spese.append(
            spreadsheet_safe_row(
                [
                    spesa.data,
                    spesa.assegnazione.commessa.cliente.ragione_sociale,
                    spesa.assegnazione.commessa.codice,
                    spesa.assegnazione.fase.nome,
                    str(spesa.assegnazione.consulente),
                    spesa.get_categoria_display(),
                    spesa.importo,
                    spesa.nota,
                    str(spesa.inserita_da),
                    "Sì" if spesa.bloccata_per_consulente else "No",
                ]
            )
        )
    for row in ws_spese.iter_rows(min_row=2):
        row[0].number_format = "dd/mm/yyyy"
        row[5].number_format = '#,##0.00 [$€-it-IT]'
    _adatta_colonne(ws_spese)

    _scrivi_aggregati(
        workbook.create_sheet("Per cliente"),
        dashboard.per_cliente,
    )
    _scrivi_aggregati(
        workbook.create_sheet("Per commessa"),
        dashboard.per_commessa,
    )
    _scrivi_aggregati(
        workbook.create_sheet("Per fase"),
        dashboard.per_fase,
    )
    _scrivi_aggregati(
        workbook.create_sheet("Per consulente"),
        dashboard.per_consulente,
    )

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
