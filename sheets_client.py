"""Conexion compartida a Google Sheets via cuenta de servicio."""

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def get_spreadsheet():
    try:
        usa_secrets = "gcp_service_account" in st.secrets
    except Exception:
        # No hay secrets.toml (caso local normal): seguimos con el archivo.
        usa_secrets = False

    if usa_secrets:
        # Desplegado en Streamlit Community Cloud: credenciales via Secrets.
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=SCOPES
        )
    else:
        # Local: credenciales desde el archivo credenciales.json.
        creds = Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(config.SPREADSHEET_ID)
