"""Utility per esportazioni CSV/XLSX sicure verso fogli di calcolo."""

FORMULA_PREFIXES = ("=", "+", "-", "@")
CONTROL_PREFIXES = ("\t", "\r", "\n")


def spreadsheet_safe(value):
    """
    Impedisce che una stringa controllabile dall'utente venga interpretata
    come formula da Excel/LibreOffice quando finisce in CSV/XLSX.

    I valori numerici/date restano invariati. Per le stringhe sospette viene
    anteposto un apostrofo, che i fogli di calcolo trattano come testo.
    """

    if not isinstance(value, str):
        return value

    if not value:
        return value

    stripped = value.lstrip()
    if (
        value.startswith(CONTROL_PREFIXES)
        or stripped.startswith(FORMULA_PREFIXES)
    ):
        return "'" + value

    return value


def spreadsheet_safe_row(values):
    return [spreadsheet_safe(value) for value in values]
