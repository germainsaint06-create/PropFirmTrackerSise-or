"""
Configuracion central de instrumentos.
Define los activos disponibles, sus decimales para display, y nombres amigables.
"""

# Lista de instrumentos disponibles en el sistema (en este orden aparecen en menus)
INSTRUMENTS = [
    "XAUUSD",   # Oro
    "US30",     # Dow Jones
    "NAS100",   # Nasdaq
    "EURUSD",
    "GBPUSD",
    "GBPJPY",
    "GBPCAD",
]

# Numero de decimales para display y validacion de inputs por instrumento
# Esto evita errores tipograficos al meter un 0 de mas o de menos
INSTRUMENT_DECIMALS = {
    "US30":   1,
    "NAS100": 1,
    "XAUUSD": 2,
    "EURUSD": 5,
    "GBPUSD": 5,
    "GBPCAD": 5,
    "GBPJPY": 3,
}

# Nombres amigables (display) por activo
INSTRUMENT_LABELS = {
    "XAUUSD": "ORO (XAUUSD)",
    "US30":   "DOW (US30)",
    "NAS100": "NASDAQ (NAS100)",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "GBPJPY": "GBPJPY",
    "GBPCAD": "GBPCAD",
}


def get_decimals(instrument):
    """Retorna decimales para un instrumento. Default 2 si no esta en config."""
    return INSTRUMENT_DECIMALS.get(instrument, 2)


def get_step(instrument):
    """Retorna step para number_input segun decimales."""
    d = get_decimals(instrument)
    return 10 ** (-d)


def get_format(instrument):
    """Retorna format string para number_input."""
    d = get_decimals(instrument)
    return f"%.{d}f"


def get_label(instrument):
    return INSTRUMENT_LABELS.get(instrument, instrument)


# Mapeo direccion long/short -> Compra/Venta para display
DIRECTION_LABELS = {"long": "Compra", "short": "Venta"}
DIRECTION_FROM_LABEL = {"Compra": "long", "Venta": "short"}
