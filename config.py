"""Configuracion del proyecto Control de Prestamos."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ID de la Hoja de Google (ya creada en tu Drive):
# https://docs.google.com/spreadsheets/d/1glEZrmTJZIBUexzPuEMUdxjxAMEKsisdO8EXPuNc64U/edit
SPREADSHEET_ID = "1glEZrmTJZIBUexzPuEMUdxjxAMEKsisdO8EXPuNc64U"

# Archivo de credenciales de la cuenta de servicio de Google (ver README.md paso 1).
# Ruta absoluta para que funcione sin importar desde donde se lance la app.
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credenciales.json")

SHEET_PRESTAMOS = "Prestamos"
SHEET_PAGOS = "Pagos"
SHEET_RESUMEN = "Resumen"
