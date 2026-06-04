import os
import time
import logging
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from fpdf import FPDF

# ---------------------------------------------------------------------------
# CONFIGURAZIONE LOGGING
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIGURAZIONE PAGINA
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Aquatime Workout Manager",
    page_icon="🚴‍♂️",
    layout="wide"
)

# ---------------------------------------------------------------------------
# COSTANTI — WORKOUT
# ---------------------------------------------------------------------------
ID_FOGLIO           = st.secrets["ID_FOGLIO"]
COLONNE_NASCOSTE    = ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"]
GOOGLE_SHEET_OFFSET = 2
CACHE_TTL           = 600
CLIENT_TTL          = 3000
MAX_PDF_PROG_LEN    = 22
MAX_PDF_LIV_LEN     = 20
MAX_INPUT_LEN       = 100

COL_KEYWORDS: dict = {
    "KMH":       lambda c: "KM/H" in c or "VELOCIT" in c,
    "KM":        lambda c: "KM " in c or c == "KM" or "DISTANZ" in c,
    "CALORIE":   lambda c: "CALOR" in c or "KCAL" in c,
    "DATA":      lambda c: "DATA" in c,
    "ATLETA":    lambda c: "ATLETA" in c or "NOME" in c or "COGNOME" in c,
    "PROGRAMMA": lambda c: "PROGRAMM" in c,
    "LIVELLO":   lambda c: "LIVELL" in c
}

# ---------------------------------------------------------------------------
# STRUTTURA DATI CLIENT / CACHE
# ---------------------------------------------------------------------------
if "cache_clienti" not in st.session_state:
    st.session_state["cache_clienti"] = None
if "timestamp_clienti" not in st.session_state:
    st.session_state["timestamp_clienti"] = 0

# ---------------------------------------------------------------------------
# FUNZIONI DI SUPPORTO E RETRY
# ---------------------------------------------------------------------------
def _retry(func, *args, **kwargs):
    for i in range(3):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning("Tentativo %d fallito per %s: %s", i+1, func.__name__, e)
            time.sleep(1.5 * (i + 1))
    return None

def force_numeric(val) -> float:
    if pd.isna(val):
        return 0.0
    s = str(val).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def clean_upper(val) -> str:
    if pd.isna(val):
        return ""
    return str(val).strip().upper()[:MAX_INPUT_LEN]

def get_exact_col(cols: list, key: str) -> str | None:
    cond = COL_KEYWORDS.get(key)
    if not cond:
        return None
    return next((c for c in cols if cond(str(c).upper())), None)

def filtra_privacy(df: pd.DataFrame) -> pd.DataFrame:
    cols_to_keep = [
        c for c in df.columns 
        if not any(k in str(c).upper() for k in COLONNE_NASCOSTE)
    ]
    return df[cols_to_keep]

# ---------------------------------------------------------------------------
# FUNZIONI DI AUTENTICAZIONE E ACCESSO AI DATI
# ---------------------------------------------------------------------------
def get_gspread_client():
    creds_dict = {
        "type":                        st.secrets["gcp_service_account"]["type"],
        "project_id":                  st.secrets["gcp_service_account"]["project_id"],
        "private_key_id":              st.secrets["gcp_service_account"]["private_key_id"],
        "private_key":                 st.secrets["gcp_service_account"]["private_key"],
        "client_email":                st.secrets["gcp_service_account"]["client_email"],
        "client_id":                   st.secrets["gcp_service_account"]["client_id"],
        "auth_uri":                    st.secrets["gcp_service_account"]["auth_uri"],
        "token_uri":                   st.secrets["gcp_service_account"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["gcp_service_account"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url":        st.secrets["gcp_service_account"]["client_x509_cert_url"]
    }
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def get_sheet():
    gc = get_gspread_client()
    return gc.open_by_key(ID_FOGLIO).sheet1

@st.cache_data(ttl=CACHE_TTL)
def fetch_all_data() -> pd.DataFrame:
    try:
        sheet = get_sheet()
        records = _retry(sheet.get_all_records)
        if records is None:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df.columns = [str(c).strip() for c in df.columns]
        
        c_data = get_exact_col(df.columns.tolist(), "DATA")
        if c_data:
            df[c_data] = pd.to_datetime(df[c_data], errors="coerce")
        return df
    except Exception as e:
        logger.error("Errore nel recupero dati: %s", e)
        return pd.DataFrame()

def invalida_df_cache():
    st.cache_data.clear()

def load_clienti_lista(df: pd.DataFrame) -> list:
    now = time.time()
    if st.session_state["cache_clienti"] and (now - st.session_state["timestamp_clienti"] < CLIENT_TTL):
        return st.session_state
