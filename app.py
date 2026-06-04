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
    "KM":        lambda c: ("KM" in c and "KM/H" not in c and "VELOCIT" not in c) or "DISTANZA" in c,
    "DATA":      lambda c: "DATA" in c and "NASCITA" not in c,
    "CALORIE":   lambda c: "CAL" in c or "KCAL" in c,
    "PROGRAMMA": lambda c: "PROGR" in c,
    "LIVELLO":   lambda c: "LIV" in c,
    "TEMP":      lambda c: "TEMP" in c or "ACQUA" in c,
}

# ---------------------------------------------------------------------------
# COSTANTI — QUADRATURA CASSA
# ---------------------------------------------------------------------------
QUADRATURE_SHEET_NAME = "Quadrature"
QUADRATURE_HEADERS = [
    "Data", "Sede", "Operatore",
    # Scontrini fiscali (input)
    "Sc_Bancomat", "Sc_Visa", "Sc_Mastercard", "Sc_Contanti",
    "Sc_Bonifico", "Sc_Assegno", "Sc_Groupon", "Sc_Gympass",
    "Sc_Amex", "Sc_Altro", "Sc_Altro_Desc",
    "Tot_Scontrini",
    # Fatture (input)
    "Ft_Bancomat", "Ft_Visa", "Ft_Mastercard", "Ft_Contanti",
    "Ft_Bonifico", "Ft_Assegno", "Ft_Groupon", "Ft_Fitprime",
    "Ft_Amex", "Ft_Aquatime", "Ft_Altro", "Ft_Altro_Desc",
    "Tot_Fatture",
    # Totale generale
    "Tot_Generale",
    # Sospeso e riconciliazione Booker
    "Sospeso", "Sospeso_Booker",
    # Altri servizi/fatture
    "AS_Altro", "AS_Aquatime", "AS_Totale",
    # Saldo cassa
    "Saldo_Iniziale", "Incasso_Contanti",
    "Pag1", "Note_Pag1", "Pag2", "Note_Pag2", "Pag3", "Note_Pag3",
    "Versamento_Banca", "Prelievo_Admin",
    "Saldo_Finale",
    "Note",
]

# ---------------------------------------------------------------------------
# AUTENTICAZIONE OPZIONALE
# ---------------------------------------------------------------------------
def check_auth() -> None:
    if "app_password" not in st.secrets:
        return
    if not st.session_state.get("authenticated", False):
        st.title("🔐 Aquatime — Accesso riservato")
        pwd = st.text_input("Password", type="password")
        if st.button("Accedi"):
            if pwd == st.secrets["app_password"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Password errata")
        st.stop()

# ---------------------------------------------------------------------------
# SICUREZZA INPUT
# ---------------------------------------------------------------------------
def sanifica(val: str) -> str:
    val = str(val).strip()[:MAX_INPUT_LEN]
    if val and val[0] in ("=", "+", "-", "@", "|", "%"):
        return "'" + val
    return val

# ---------------------------------------------------------------------------
# ACCESSO AI DATI — WORKOUT
# ---------------------------------------------------------------------------
@st.cache_resource(ttl=CLIENT_TTL)
def get_gspread_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)


@st.cache_resource(ttl=CLIENT_TTL)
def get_sheet():
    return get_gspread_client().open_by_key(ID_FOGLIO).sheet1


@st.cache_resource(ttl=CLIENT_TTL)
def get_spreadsheet():
    """Oggetto spreadsheet cachato — evita di riaprirlo ad ogni chiamata."""
    return get_gspread_client().open_by_key(ID_FOGLIO)


@st.cache_data(ttl=CACHE_TTL)
def fetch_all_data(id_foglio: str) -> list[dict]:
    client = get_gspread_client()
    sheet  = client.open_by_key(id_foglio).sheet1
    data   = sheet.get_all_records(numericise_ignore=['all'])
    result = []
    for i, row in enumerate(data):
        clean = {str(k).strip(): v for k, v in row.items()}
        clean["GOOGLE_SHEET_ROW"] = i + GOOGLE_SHEET_OFFSET
        if clean.get("Nome") and str(clean["Nome"]).strip():
            result.append(clean)
    return result

# ---------------------------------------------------------------------------
# ACCESSO AI DATI — QUADRATURA CASSA
# ---------------------------------------------------------------------------
def get_or_create_quadrature_sheet() -> gspread.Worksheet:
    spreadsheet = get_spreadsheet()
    try:
        ws = spreadsheet.worksheet(QUADRATURE_SHEET_NAME)
        if not ws.row_values(1):
            ws.append_row(QUADRATURE_HEADERS)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title=QUADRATURE_SHEET_NAME,
            rows=2000,
            cols=len(QUADRATURE_HEADERS)
        )
        ws.append_row(QUADRATURE_HEADERS)
        logger.info("Creato tab '%s'", QUADRATURE_SHEET_NAME)
    return ws


def get_last_saldo_iniziale(sede: str) -> float:
    try:
        records = fetch_quadrature_data(sede)
        if records:
            return force_numeric(records[-1].get("Saldo_Finale", 0))
    except Exception as e:
        logger.error("Errore recupero saldo iniziale: %s", e)
    return 0.0


@st.cache_data(ttl=60)
def fetch_quadrature_data(sede: str) -> list[dict]:
    try:
        ws = get_or_create_quadrature_sheet()
        all_records = ws.get_all_records()
        result = []
        for i, r in enumerate(all_records):
            if str(r.get("Sede", "")).strip() == sede:
                r["SHEET_ROW"] = i + 2
            result.append(r)
        return result
    except Exception as e:
        logger.error("Errore fetch quadrature: %s", e)
        return []

# ---------------------------------------------------------------------------
# UTILITY — WORKOUT
# ---------------------------------------------------------------------------
def force_numeric(val) -> float:
    """Converte qualsiasi valore (None, stringa con virgola, numero) in float."""
    if val is None or val == "":
        return 0.0
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0

_nv = force_numeric


def normalizza_numerici(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        col_up = str(col).upper().strip()
        is_numeric_col = (
            COL_KEYWORDS["KMH"](col_up)
            or COL_KEYWORDS["KM"](col_up)
            or COL_KEYWORDS["CALORIE"](col_up)
            or COL_KEYWORDS["TEMP"](col_up)
        )
        if is_numeric_col:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", ".", regex=False).str.strip(),
                errors="coerce"
            ).fillna(0.0)
    return df


def get_df_normalizzato(dati_raw: list[dict]) -> pd.DataFrame:
    if "data_version" not in st.session_state:
        st.session_state.data_version = 0
    chiave = f"df_norm_{st.session_state.data_version}"
    if chiave not in st.session_state:
        st.session_state[chiave] = normalizza_numerici(pd.DataFrame(dati_raw))
    return st.session_state[chiave].copy()


def invalida_df_cache():
    versione_corrente = st.session_state.get("data_version", 0)
    chiave_vecchia = f"df_norm_{versione_corrente}"
    if chiave_vecchia in st.session_state:
        del st.session_state[chiave_vecchia]
    st.session_state.data_version = versione_corrente + 1


def filtra_privacy(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        c for c in df.columns
        if not any(x in str(c).upper() for x in COLONNE_NASCOSTE)
        and c != "GOOGLE_SHEET_ROW"
    ]
    return df[cols].dropna(how="all").copy()


def get_exact_col(columns, target: str):
    matcher = COL_KEYWORDS.get(target)
    if not matcher:
        return None
    for col in columns:
        if matcher(str(col).upper().strip()):
            return col
    return None


def _retry(fn, *args, max_retries: int = 3, **kwargs) -> bool:
    for attempt in range(max_retries):
        try:
            fn(*args, **kwargs)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("Tentativo %d/%d fallito (%s), retry tra %ds",
                               attempt + 1, max_retries, e, wait)
                time.sleep(wait)
            else:
                logger.error("Operazione fallita dopo %d tentativi: %s", max_retries, e)
    return False

# ---------------------------------------------------------------------------
# UTILITY — QUADRATURA CASSA
# ---------------------------------------------------------------------------
def calcola_quadratura(inp: dict) -> dict:
    d = inp.copy()
    d["Tot_Scontrini"] = round(sum([
        d.get("Sc_Bancomat", 0.0), d.get("Sc_Visa", 0.0),
        d.get("Sc_Mastercard", 0.0), d.get("Sc_Contanti", 0.0),
        d.get("Sc_Bonifico", 0.0), d.get("Sc_Assegno", 0.0),
        d.get("Sc_Groupon", 0.0), d.get("Sc_Gympass", 0.0),
        d.get("Sc_Amex", 0.0), d.get("Sc_Altro", 0.0),
    ]), 2)

    d["Tot_Fatture"] = round(sum([
        d.get("Ft_Bancomat", 0.0), d.get("Ft_Visa", 0.0),
        d.get("Ft_Mastercard", 0.0), d.get("Ft_Contanti", 0.0),
        d.get("Ft_Bonifico", 0.0), d.get("Ft_Assegno", 0.0),
        d.get("Ft_Groupon", 0.0), d.get("Ft_Fitprime", 0.0),
        d.get("Ft_Amex", 0.0), d.get("Ft_Aquatime", 0.0),
        d.get("Ft_Altro", 0.0),
    ]), 2)

    d["Tot_Generale"] = round(d["Tot_Scontrini"] + d["Tot_Fatture"], 2)
    d["Sospeso_Booker"] = round(d["Tot_Generale"] + d.get("Sospeso", 0.0), 2)
    d["AS_Totale"] = round(d.get("AS_Altro", 0.0) + d.get("AS_Aquatime", 0.0), 2)
    d["Incasso_Contanti"] = round(
        d.get("Sc_Contanti", 0.0) + d.get("Ft_Contanti", 0.0), 2
    )
    d["Saldo_Finale"] = round(
        d.get("Saldo_Iniziale", 0.0)
        + d["Incasso_Contanti"]
        - d.get("Pag1", 0.0)
        - d.get("Pag2", 0.0)
        - d.get("Pag3", 0.0)
        - d.get("Versamento_Banca", 0.0)
        - d.get("Prelievo_Admin", 0.0),
        2
    )
    return d


def _fmt(val) -> str:
    f = force_numeric(val)
    return f"EUR {f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ---------------------------------------------------------------------------
# GENERAZIONE PDF — WORKOUT
# ---------------------------------------------------------------------------
def generate_pdf(df_atleta: pd.DataFrame, nome_atleta: str) -> bytes | None:
    try:
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        cols   = df_atleta.columns.tolist()
        c_data = get_exact_col(cols, "DATA")
        c_km   = get_exact_col(cols, "KM")
        c_kmh  = get_exact_col(cols, "KMH")
        c_cal  = get_exact_col(cols, "CALORIE")
        c_prog = get_exact_col(cols, "PROGRAMMA")
        c_liv  = get_exact_col(cols, "LIVELLO")
        c_temp = get_exact_col(cols, "TEMP")

        km_vals = pd.to_numeric(df_atleta[c_km].astype(str).str.replace(",", ".", regex=False), errors="coerce").fillna(0.0) if c_km else pd.Series([0.0])
        kmh_avg = df_atleta[c_kmh].apply(force_numeric).mean() if c_kmh else 0.0
        cal_avg = df_atleta[c_cal].apply(force_numeric).mean() if c_cal else 0.0

        pdf.set_fill_color(0, 80, 158)
        pdf.rect(0, 0, 210, 40, "F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("helvetica", "B", 20)
        pdf.set_y(12)
        pdf.cell(0, 10, "AQUATIME PERFORMANCE", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 12)
        pdf.cell(0, 10, f"REPORT: {nome_atleta.upper()}", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.set_y(45)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "B", 11)
        pdf.set_fill_color(235, 235, 235)
        pdf.cell(63, 10, f"KM TOTALI: {km_vals.sum():.2f}", 1, 0, "C", True)
        pdf.cell(63, 10, f"KM/H MEDI: {kmh_avg:.1f}",       1, 0, "C", True)
        pdf.cell(64, 10, f"KCAL MEDIE: {cal_avg:.0f}",      1, 1, "C", True)
        pdf.ln(5)

        # Larghezze riadattate: 22+35+30+12+12+15+15+49 = 190mm (con Temp. Acqua)
        col_widths = [22, 35, 30, 12, 12, 15, 15, 49]
        headers    = ["Data", "Programma", "Livello", "Km", "Km/h", "Cal.", "T.H2O", "Note"]
        pdf.set_font("helvetica", "B", 9)
        pdf.set_fill_color(0, 80, 158)
        pdf.set_text_color(255, 255, 255)
        for w, h in zip(col_widths, headers):
            pdf.cell(w, 8, h, 1, 0, "C", True)
        pdf.ln()

        c_note = next((c for c in cols if str(c).strip().upper() == "NOTE"), None)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "", 8)
        for _, row in df_atleta.iterrows():
            data_val = row.get(c_data, "")
            if hasattr(data_val, "strftime"):
                solo_data = data_val.strftime("%d/%m/%Y")
            else:
                data_str = str(data_val).split(" ")[0] if " " in str(data_val) else str(data_val)
                try:
                    solo_data = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                except ValueError:
                    solo_data = data_str

            note_val = str(row.get(c_note, ""))[:38] if c_note else ""
            temp_val = f"{force_numeric(row.get(c_temp, 0)):.2f}°C" if c_temp else "0.00°C"

            pdf.cell(col_widths[0], 7, solo_data,                                   1, 0, "C")
            pdf.cell(col_widths[1], 7, str(row.get(c_prog, ""))[:MAX_PDF_PROG_LEN], 1, 0, "L")
            pdf.cell(col_widths[2], 7, str(row.get(c_liv,  ""))[:MAX_PDF_LIV_LEN],  1, 0, "L")
            pdf.cell(col_widths[3], 7, str(row.get(c_km,   "0")),                   1, 0, "C")
            pdf.cell(col_widths[4], 7, str(row.get(c_kmh,  "0")),                   1, 0, "C")
            pdf.cell(col_widths[5], 7, str(row.get(c_cal,  "0")),                   1, 0, "C")
            pdf.cell(col_widths[6], 7, temp_val,                                    1, 0, "C")
            pdf.cell(col_widths[7], 7, note_val,                                    1, 1, "L")

        out = pdf.output()
        return bytes(out) if isinstance(out, bytearray) else out

    except Exception as e:
        logger.error("Errore PDF workout: %s", e)
        st.error(f"Errore generazione PDF: {e}")
        return None

# ---------------------------------------------------------------------------
# GENERAZIONE PDF — QUADRATURA CASSA
# ---------------------------------------------------------------------------
def genera_pdf_quadratura(d: dict) -> bytes | None:
    try:
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()

        BLUE  = (0, 80, 158)
        LGRAY = (235, 235, 235)
        BLACK = (0, 0, 0)
        WHITE = (255, 255, 255)

        LM = 8
        PW = 194
        CW = 95

        pdf.set_fill_color(*BLUE)
        pdf.rect(0, 0, 210, 18, "F")
        pdf.set_text_color(*WHITE)
        pdf.set_font("helvetica", "B", 14)
        pdf.set_xy(LM, 3)
        pdf.cell(PW, 7, "AQUATIME ROMA - QUADRATURA CASSA GIORNALIERA", align="C")
        pdf.set_font("helvetica", "B", 11)
        pdf.set_xy(LM, 11)
        pdf.cell(PW, 5, f"SEDE: {d.get('Sede','').upper()}", align="C")

        pdf.set_text_color(*BLACK)
        pdf.set_fill_color(*LGRAY)
        pdf.set_font("helvetica", "B", 9)
        pdf.set_xy(LM, 21)
        pdf.cell(40, 7, "DATA:", 1, 0, "L", True)
        pdf.set_font("helvetica", "", 9)
        pdf.cell(55, 7, str(d.get("Data", "")), 1, 0, "L")
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(35, 7, "OPERATORE:", 1, 0, "L", True)
        pdf.set_font("helvetica", "", 9)
        pdf.cell(PW - 40 - 55 - 35, 7, str(d.get("Operatore", "")), 1, 1, "L")

        y_after_info = pdf.get_y() + 3

        def section_header(title: str, x: float, y: float, w: float):
            pdf.set_xy(x, y)
            pdf.set_fill_color(*BLUE)
            pdf.set_text_color(*WHITE)
            pdf.set_font("helvetica", "B", 8)
            pdf.cell(w, 6, title, 1, 0, "C", True)
            pdf.set_text_color(*BLACK)

        def payment_row(label: str, val: float, x: float, y: float,
                        lw: float = 52, vw: float = 43, fill: bool = False):
            pdf.set_xy(x, y)
            pdf.set_fill_color(*LGRAY)
            pdf.set_font("helvetica", "", 7)
            pdf.cell(lw, 5.5, label, 1, 0, "L", fill)
            pdf.set_font("helvetica", "B" if fill else "", 7)
            pdf.cell(vw, 5.5, _fmt(val), 1, 0, "R", fill)

        x_left  = LM
        x_right = LM + CW + 4
        y_cur   = y_after_info

        section_header("SCONTRINI FISCALI", x_left, y_cur, CW)
        section_header("FATTURE",           x_right, y_cur, CW)
        y_cur += 6

        scontrini_rows = [
            ("Bancomat",    d.get("Sc_Bancomat",   0.0)),
            ("Visa",        d.get("Sc_Visa",        0.0)),
            ("Mastercard",  d.get("Sc_Mastercard",  0.0)),
            ("Contanti",    d.get("Sc_Contanti",    0.0)),
            ("Bonifico",    d.get("Sc_Bonifico",    0.0)),
            ("Assegno",     d.get("Sc_Assegno",     0.0)),
            ("Groupon",     d.get("Sc_Groupon",     0.0)),
            ("Gympass",     d.get("Sc_Gympass",     0.0)),
            ("Amex",        d.get("Sc_Amex",        0.0)),
            (f"Altro ({d.get('Sc_Altro_Desc','')[:12]})", d.get("Sc_Altro", 0.0)),
        ]
        fatture_rows = [
            ("Bancomat",    d.get("Ft_Bancomat",    0.0)),
            ("Visa",        d.get("Ft_Visa",        0.0)),
            ("Mastercard",  d.get("Ft_Mastercard",  0.0)),
            ("Contanti",    d.get("Ft_Contanti",    0.0)),
            ("Bonifico",    d.get("Ft_Bonifico",    0.0)),
            ("Assegno",     d.get("Ft_Assegno",     0.0)),
            ("Groupon",     d.get("Ft_Groupon",     0.0)),
            ("Fitprime",    d.get("Ft_Fitprime",    0.0)),
            ("Amex",        d.get("Ft_Amex",        0.0)),
            ("Aquatime P/T",d.get("Ft_Aquatime",    0.0)),
            (f"Altro ({d.get('Ft_Altro_Desc','')[:12]})", d.get("Ft_Altro", 0.0)),
        ]

        max_rows = max(len(scontrini_rows), len(fatture_rows))
        for i in range(max_rows):
            if i < len(scontrini_rows):
                payment_row(scontrini_rows[i][0], scontrini_rows[i][1], x_left, y_cur)
            if i < len(fatture_rows):
                payment_row(fatture_rows[i][0], fatture_rows[i][1], x_right, y_cur)
            y_cur += 5.5

        payment_row("TOTALE SCONTRINI", d["Tot_Scontrini"], x_left,  y_cur, fill=True)
        payment_row("TOTALE FATTURE",   d["Tot_Fatture"],   x_right, y_cur, fill=True)
        y_cur += 5.5 + 4

        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*BLUE)
        pdf.set_text_color(*WHITE)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(130, 8, "TOTALE GENERALE (Scontrini + Fatture)", 1, 0, "L", True)
        pdf.cell(PW - 130, 8, _fmt(d["Tot_Generale"]), 1, 1, "R", True)
        pdf.set_text_color(*BLACK)
        y_cur = pdf.get_y() + 3

        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*LGRAY)
        pdf.set_font("helvetica", "B", 8)
        pdf.cell(PW, 5, "RICONCILIAZIONE BOOKER", 1, 1, "C", True)
        y_cur = pdf.get_y()

        LW2 = 130
        VW2 = PW - LW2
        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*WHITE)
        pdf.set_font("helvetica", "", 8)
        pdf.cell(LW2, 6, "Totale Booker (= Totale Generale)", 1, 0, "L", False)
        pdf.set_font("helvetica", "B", 8)
        pdf.cell(VW2, 6, _fmt(d["Tot_Generale"]), 1, 1, "R", False)
        y_cur = pdf.get_y()

        pdf.set_xy(LM, y_cur)
        pdf.set_font("helvetica", "", 8)
        pdf.cell(LW2, 6, "Sospeso (K15)", 1, 0, "L", False)
        pdf.set_font("helvetica", "B", 8)
        pdf.cell(VW2, 6, _fmt(d.get("Sospeso", 0.0)), 1, 1, "R", False)
        y_cur = pdf.get_y()

        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*LGRAY)
        pdf.set_font("helvetica", "B", 8)
        pdf.cell(LW2, 6, "Sospeso + Totale Booker (O15)", 1, 0, "L", True)
        pdf.cell(VW2, 6, _fmt(d["Sospeso_Booker"]), 1, 1, "R", True)
        pdf.set_text_color(*BLACK)
        y_cur = pdf.get_y() + 3

        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*LGRAY)
        pdf.set_font("helvetica", "B", 8)
        pdf.cell(PW, 5, "ALTRI SERVIZI / FATTURE", 1, 1, "C", True)
        y_cur = pdf.get_y()

        as_col = PW / 3
        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*BLUE)
        pdf.set_text_color(*WHITE)
        pdf.set_font("helvetica", "B", 7)
        pdf.cell(as_col, 5.5, "ALTRO", 1, 0, "C", True)
        pdf.cell(as_col, 5.5, "AQUATIME", 1, 0, "C", True)
        pdf.cell(as_col, 5.5, "TOTALE", 1, 1, "C", True)
        pdf.set_text_color(*BLACK)
        y_cur = pdf.get_y()

        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*WHITE)
        pdf.set_font("helvetica", "", 8)
        pdf.cell(as_col, 6, _fmt(d.get("AS_Altro", 0.0)),   1, 0, "C", False)
        pdf.cell(as_col, 6, _fmt(d.get("AS_Aquatime", 0.0)),1, 0, "C", False)
        pdf.set_font("helvetica", "B", 8)
        pdf.cell(as_col, 6, _fmt(d.get("AS_Totale", 0.0)),  1, 1, "C", False)
        y_cur = pdf.get_y() + 3

        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*BLUE)
        pdf.set_text_color(*WHITE)
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(PW, 6, "SALDO CASSA CONTANTI", 1, 1, "C", True)
        pdf.set_text_color(*BLACK)
        y_cur = pdf.get_y()

        LW_SALDO = 110
        VW_SALDO = PW - LW_SALDO

        def saldo_row(label: str, val, bold_val: bool = False, fill_color=None, text_color=BLACK):
            nonlocal y_cur
            fc = fill_color if fill_color else WHITE
            pdf.set_xy(LM, y_cur)
            pdf.set_fill_color(*fc)
            pdf.set_font("helvetica", "", 8)
            pdf.cell(LW_SALDO, 6.5, label, 1, 0, "L", True)
            pdf.set_font("helvetica", "B" if bold_val else "", 8)
            pdf.set_text_color(*text_color)
            pdf.cell(VW_SALDO, 6.5, _fmt(val), 1, 1, "R", True)
            pdf.set_text_color(*BLACK)
            y_cur += 6.5

        saldo_row("Saldo Iniziale Cassa Contanti",         d.get("Saldo_Iniziale",    0.0), fill_color=LGRAY)
        saldo_row("(+) Incasso Contanti del giorno",       d.get("Incasso_Contanti",  0.0))
        note1 = f"(-) Pagamento 1 - {d.get('Note_Pag1','')[:30]}" if d.get("Note_Pag1") else "(-) Pagamento 1"
        note2 = f"(-) Pagamento 2 - {d.get('Note_Pag2','')[:30]}" if d.get("Note_Pag2") else "(-) Pagamento 2"
        note3 = f"(-) Pagamento 3 - {d.get('Note_Pag3','')[:30]}" if d.get("Note_Pag3") else "(-) Pagamento 3"
        saldo_row(note1, d.get("Pag1", 0.0))
        saldo_row(note2, d.get("Pag2", 0.0))
        saldo_row(note3, d.get("Pag3", 0.0))
        saldo_row("(-) Versamento in Banca",               d.get("Versamento_Banca",  0.0))
        saldo_row("(-) Prelievo Amministratore",           d.get("Prelievo_Admin",    0.0))

        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*BLUE)
        pdf.set_text_color(*WHITE)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(LW_SALDO, 8, "SALDO FINALE CASSA CONTANTI", 1, 0, "L", True)
        pdf.cell(VW_SALDO, 8, _fmt(d["Saldo_Finale"]), 1, 1, "R", True)
        y_cur = pdf.get_y() + 4

        nota = str(d.get("Note", "")).strip()
        if nota:
            pdf.set_xy(LM, y_cur)
            pdf.set_fill_color(*LGRAY)
            pdf.set_text_color(*BLACK)
            pdf.set_font("helvetica", "B", 8)
            pdf.cell(PW, 5, "NOTE", 1, 1, "L", True)
            y_cur = pdf.get_y()
            pdf.set_xy(LM, y_cur)
            pdf.set_fill_color(*WHITE)
            pdf.set_font("helvetica", "", 8)
            pdf.multi_cell(PW, 5, nota, border=1, align="L")

        out = pdf.output()
        return bytes(out) if isinstance(out, bytearray) else out
    except Exception as e:
        logger.error("Errore PDF quadratura: %s", e)
        st.error(f"Errore generazione PDF quadratura: {e}")
        return None

# ---------------------------------------------------------------------------
# FORM QUADRATURA CASSA
# ---------------------------------------------------------------------------
def render_form_quadratura(sede: str) -> None:
    if st.button("← Torna alla Home"):
        for k in list(st.session_state.keys()):
            if k.startswith("confirm_del_"):
                del st.session_state[k]
        st.session_state.pagina = "home"
        st.rerun()

    st.subheader(f"📋 Quadratura Cassa — {sede}")
    tab_nuova, tab_cerca, tab_rivedi = st.tabs([
        "➕ Nuova Quadratura", "🔍 Cerca per Giorno", "📋 Rivedi / Cancella"
    ])

    with tab_nuova:
        if "qfid" not in st.session_state:
            st.session_state.qfid = 0
        qfid = st.session_state.qfid

        if f"saldo_init_loaded_{sede}_{qfid}" not in st.session_state:
            st.session_state[f"saldo_init_loaded_{sede}_{qfid}"] = get_last_saldo_iniziale(sede)
        saldo_precedente = st.session_state[f"saldo_init_loaded_{sede}_{qfid}"]

        with st.container(border=True):
            st.markdown("**📅 Intestazione**")
            c1, c2 = st.columns(2)
            data_q = c1.date_input("Data *", value=datetime.today(), format="DD/MM/YYYY", key=f"qdata_{qfid}")
            
            OPERATORI = [
                "Barbara Iorio", "Barbara Pasqualini", "Daniela Bissieres", "Francesca Ionta",
                "Jacopo Vendetti", "Raffaele Picinni", "Stefano Lampis", "Sofia Amore", "Gianluca Nania", "Altro..."
            ]
            op_sel = c2.selectbox("Operatore *", OPERATORI, index=None, placeholder="Scegli operatore...", key=f"qop_sel_{qfid}")
            operatore = ""
            if op_sel == "Altro...":
                operatore = st.text_input("Specificare operatore *", key=f"qop_txt_{qfid}", max_chars=MAX_INPUT_LEN)
            elif op_sel:
                operatore = op_sel

            st.divider()
            st.markdown("**🧾 Scontrini Fiscali**")
            cs1, cs2, cs3, cs4, cs5 = st.columns(5)
            sc_bancomat = cs1.text_input("Bancomat", key=f"sc_bk_{qfid}", placeholder="0.00")
            sc_visa     = cs2.text_input("Visa", key=f"sc_vs_{qfid}", placeholder="0.00")
            sc_master   = cs3.text_input("Mastercard", key=f"sc_mc_{qfid}", placeholder="0.00")
            sc_contanti = cs4.text_input("Contanti", key=f"sc_ct_{qfid}", placeholder="0.00")
            sc_bonifico = cs5.text_input("Bonifico", key=f"sc_bn_{qfid}", placeholder="0.00")

            cs6, cs7, cs8, cs9, cs10 = st.columns(5)
            sc_assegno  = cs6.text_input("Assegno", key=f"sc_as_{qfid}", placeholder="0.00")
            sc_groupon  = cs7.text_input("Groupon", key=f"sc_gp_{qfid}", placeholder="0.00")
            sc_gympass  = cs8.text_input("Gympass", key=f"sc_gym_{qfid}", placeholder="0.00")
            sc_amex     = cs9.text_input("Amex", key=f"sc_amx_{qfid}", placeholder="0.00")
            sc_altro    = cs10.text_input("Altro", key=f"sc_alt_{qfid}", placeholder="0.00")
            sc_altro_desc = st.text_input("Specificare Altro Scontrini", key=f"sc_altd_{qfid}", max_chars=50)

            tot_sc = round(_nv(sc_bancomat)+_nv(sc_visa)+_nv(sc_master)+_nv(sc_contanti)+_nv(sc_bonifico)+
                           _nv(sc_assegno)+_nv(sc_groupon)+_nv(sc_gympass)+_nv(sc_amex)+_nv(sc_altro), 2)
            st.info(f"**Totale Scontrini: {_fmt(tot_sc)}**")

            st.divider()
            st.markdown("**📄 Fatture**")
            cf1, cf2, cf3, cf4, cf5 = st.columns(5)
            ft_bancomat = cf1.text_input("Bancomat", key=f"ft_bk_{qfid}", placeholder="0.00")
            ft_visa     = cf2.text_input("Visa", key=f"ft_vs_{qfid}", placeholder="0.00")
            ft_master   = cf3.text_input("Mastercard", key=f"ft_mc_{qfid}", placeholder="0.00")
            ft_contanti = cf4.text_input("Contanti", key=f"ft_ct_{qfid}", placeholder="0.00")
            ft_bonifico = cf5.text_input("Bonifico", key=f"ft_bn_{qfid}", placeholder="0.00")

            cf6, cf7, cf8, cf9, cf10, cf11 = st.columns(6)
            ft_assegno  = cf6.text_input("Assegno", key=f"ft_as_{qfid}", placeholder="0.00")
            ft_groupon  = cf7.text_input("Groupon", key=f"ft_gp_{qfid}", placeholder="0.00")
            ft_fitprime = cf8.text_input("Fitprime", key=f"ft_fp_{qfid}", placeholder="0.00")
            ft_amex     = cf9.text_input("Amex", key=f"ft_amx_{qfid}", placeholder="0.00")
            ft_aquatime = cf10.text_input("Aquatime", key=f"ft_aq_{qfid}", placeholder="0.00")
            ft_altro    = cf11.text_input("Altro", key=f"ft_alt_{qfid}", placeholder="0.00")
            ft_altro_desc = st.text_input("Specificare Altro Fatture", key=f"ft_altd_{qfid}", max_chars=50)

            tot_ft = round(_nv(ft_bancomat)+_nv(ft_visa)+_nv(ft_master)+_nv(ft_contanti)+_nv(ft_bonifico)+
                           _nv(ft_assegno)+_nv(ft_groupon)+_nv(ft_fitprime)+_nv(ft_amex)+_nv(ft_aquatime)+_nv(ft_altro), 2)
            st.info(f"**Totale Fatture: {_fmt(tot_ft)}**")

            st.divider()
            st.markdown("**💰 Riconciliazione Booker e Altri Servizi**")
            cb1, cb2, cb3 = st.columns(3)
            sospeso = cb1.text_input("Sospeso (K15)", key=f"q_sosp_{qfid}", placeholder="0.00")
            as_altro = cb2.text_input("Altri Servizi — Altro", key=f"q_asal_{qfid}", placeholder="0.00")
            as_aqua = cb3.text_input("Altri Servizi — Aquatime", key=f"q_asaq_{qfid}", placeholder="0.00")

            st.divider()
            st.markdown("**🏧 Movimenti di Cassa**")
            st.write(f"Saldo Iniziale Cassa Contanti Precedente: **{_fmt(saldo_precedente)}**")
            
            cc1, cc2 = st.columns(2)
            override_saldo_init = cc1.toggle("Modifica Saldo Iniziale manually", key=f"q_ovr_si_{qfid}")
            saldo_iniziale_form = saldo_precedente
            if override_saldo_init:
                s_init_inp = cc2.text_input("Nuovo Saldo Iniziale Cassa Contanti", key=f"q_si_val_{qfid}", placeholder="0.00")
                if s_init_inp.strip():
                    saldo_iniziale_form = _nv(s_init_inp)

            cm1, cm2, cm3 = st.columns(3)
            pag1 = cm1.text_input("Pagamento 1", key=f"q_p1_{qfid}", placeholder="0.00")
            note_p1 = cm1.text_input("Nota Pagamento 1", key=f"q_np1_{qfid}", max_chars=50)
            pag2 = cm2.text_input("Pagamento 2", key=f"q_p2_{qfid}", placeholder="0.00")
            note_p2 = cm2.text_input("Nota Pagamento 2", key=f"q_np2_{qfid}", max_chars=50)
            pag3 = cm3.text_input("Pagamento 3", key=f"q_p3_{qfid}", placeholder="0.00")
            note_p3 = cm3.text_input("Nota Pagamento 3", key=f"q_np3_{qfid}", max_chars=50)

            cm4, cm5 = st.columns(2)
            vers_banca = cm4.text_input("Versamento in Banca", key=f"q_vb_{qfid}", placeholder="0.00")
            prel_admin = cm5.text_input("Prelievo Amministratore", key=f"q_pa_{qfid}", placeholder="0.00")

            st.divider()
            st.markdown("**📝 Note Generali**")
            note_gen = st.text_area("Note", key=f"q_note_{qfid}", max_chars=300)

            # Calcolo Live Anteprima
            payload_live = {
                "Sc_Bancomat": _nv(sc_bancomat), "Sc_Visa": _nv(sc_visa), "Sc_Mastercard": _nv(sc_master),
                "Sc_Contanti": _nv(sc_contanti), "Sc_Bonifico": _nv(sc_bonifico), "Sc_Assegno": _nv(sc_assegno),
                "Sc_Groupon": _nv(sc_groupon), "Sc_Gympass": _nv(sc_gympass), "Sc_Amex": _nv(sc_amex), "Sc_Altro": _nv(sc_altro),
                "Ft_Bancomat": _nv(ft_bancomat), "Ft_Visa": _nv(ft_visa), "Ft_Mastercard": _nv(ft_master),
                "Ft_Contanti": _nv(ft_contanti), "Ft_Bonifico": _nv(ft_bonifico), "Ft_Assegno": _nv(ft_assegno),
                "Ft_Groupon": _nv(ft_groupon), "Ft_Fitprime": _nv(ft_fitprime), "Ft_Amex": _nv(ft_amex),
                "Ft_Aquatime": _nv(ft_aquatime), "Ft_Altro": _nv(ft_altro),
                "Sospeso": _nv(sospeso), "AS_Altro": _nv(as_altro), "AS_Aquatime": _nv(as_aqua),
                "Saldo_Iniziale": saldo_iniziale_form, "Pag1": _nv(pag1), "Pag2": _nv(pag2), "Pag3": _nv(pag3),
                "Versamento_Banca": _nv(vers_banca), "Prelievo_Admin": _nv(prel_admin)
            }
            res_live = calcola_quadratura(payload_live)
            st.metric(label="Saldo Finale Cassa Stimato", value=_fmt(res_live["Saldo_Finale"]))

            st.write("")
            _, col_btn, _ = st.columns([2, 1, 2])
            if col_btn.button("💾 Salva Quadratura", use_container_width=True):
                if not operatore:
                    st.error("❌ Errore: Campo 'Operatore' obbligatorio.")
                else:
                    with st.spinner("Salvataggio in corso..."):
                        final_data = {
                            "Data": data_q.strftime("%d/%m/%Y"), "Sede": sede, "Operatore": sanifica(operatore),
                            "Sc_Bancomat": _nv(sc_bancomat), "Sc_Visa": _nv(sc_visa), "Sc_Mastercard": _nv(sc_master),
                            "Sc_Contanti": _nv(sc_contanti), "Sc_Bonifico": _nv(sc_bonifico), "Sc_Assegno": _nv(sc_assegno),
                            "Sc_Groupon": _nv(sc_groupon), "Sc_Gympass": _nv(sc_gympass), "Sc_Amex": _nv(sc_amex),
                            "Sc_Altro": _nv(sc_altro), "Sc_Altro_Desc": sanifica(sc_altro_desc),
                            "Ft_Bancomat": _nv(ft_bancomat), "Ft_Visa": _nv(ft_visa), "Ft_Mastercard": _nv(ft_master),
                            "Ft_Contanti": _nv(ft_contanti), "Ft_Bonifico": _nv(ft_bonifico), "Ft_Assegno": _nv(ft_assegno),
                            "Ft_Groupon": _nv(ft_groupon), "Ft_Fitprime": _nv(ft_fitprime), "Ft_Amex": _nv(ft_amex),
                            "Ft_Aquatime": _nv(ft_aquatime), "Ft_Altro": _nv(ft_altro), "Ft_Altro_Desc": sanifica(ft_altro_desc),
                            "Sospeso": _nv(sospeso), "AS_Altro": _nv(as_altro), "AS_Aquatime": _nv(as_aqua),
                            "Saldo_Iniziale": saldo_iniziale_form, "Pag1": _nv(pag1), "Note_Pag1": sanifica(note_p1),
                            "Pag2": _nv(pag2), "Note_Pag2": sanifica(note_p2), "Pag3": _nv(pag3), "Note_Pag3": sanifica(note_p3),
                            "Versamento_Banca": _nv(vers_banca), "Prelievo_Admin": _nv(prel_admin), "Note": sanifica(note_gen)
                        }
                        computed = calcola_quadratura(final_data)
                        final_data.update(computed)

                        riga_excel = [final_data.get(h, "") for h in QUADRATURE_HEADERS]
                        ws = get_or_create_quadrature_sheet()
                        ok = _retry(ws.append_row, riga_excel)
                        if ok:
                            fetch_quadrature_data.clear()
                            st.session_state.qfid += 1
                            st.success("✅ Quadratura salvata con successo!")
                            st.rerun()
                        else:
                            st.error("❌ Errore durante l'append sul Google Sheet.")

    with tab_cerca:
        st.markdown("**🔍 Cerca Quadratura Cassa Storica**")
        c_search_1, c_search_2 = st.columns(2)
        search_date = c_search_1.date_input("Seleziona la data da cercare:", value=datetime.today(), format="DD/MM/YYYY")
        if c_search_2.button("🔍 Avvia Ricerca", use_container_width=True):
            records = fetch_quadrature_data(sede)
            dt_str = search_date.strftime("%d/%m/%Y")
            match = [r for r in records if r.get("Data") == dt_str]
            if match:
                st.success(f"Trovata riga per il giorno {dt_str}!")
                for m in match:
                    st.json(m)
                    pdf_bytes = genera_pdf_quadratura(m)
                    if pdf_bytes:
                        st.download_button(f"📥 Scarica PDF Quadratura ({m.get('Operatore','')})", pdf_bytes, f"Quadratura_{sede}_{dt_str.replace('/','-')}.pdf", "application/pdf")
            else:
                st.warning("Nessuna quadratura trovata per questa data.")

    with tab_rivedi:
        st.markdown("**📋 Ultime 10 quadrature inserite per questa sede**")
        records = fetch_quadrature_data(sede)
        if records:
            df_q = pd.DataFrame(records).tail(10)
            st.dataframe(df_q, use_container_width=True)
            st.write("---")
            st.markdown("**🗑️ Elimina una Quadratura**")
            opzioni_del = []
            for r in records[-10:]:
                label_del = f"Riga {r['SHEET_ROW']} | Data: {r.get('Data','')} | Op: {r.get('Operatore','')}"
                opzioni_del.append({"label": label_del, "row": r["SHEET_ROW"]})
            
            scelta_del = st.selectbox("Seleziona quale riga eliminare permanentemente:", opzioni_del, format_func=lambda x: x["label"], index=None, key=f"del_quad_{sede}")
            if scelta_del:
                confirm_key = f"confirm_del_{sede}_{scelta_del['row']}"
                if confirm_key not in st.session_state:
                    st.session_state[confirm_key] = False

                if not st.session_state[confirm_key]:
                    if st.button("🚨 Richiedi Eliminazione", type="primary", use_container_width=True):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    st.warning(f"⚠️ Confermi l'eliminazione definitiva della riga {scelta_del['row']}?")
                    c_b1, c_b2 = st.columns(2)
                    if c_b1.button("✅ Sì, procedi", use_container_width=True):
                        ws = get_or_create_quadrature_sheet()
                        if _retry(ws.delete_rows, scelta_del["row"]):
                            fetch_quadrature_data.clear()
                            del st.session_state[confirm_key]
                            st.success("Eliminata correttamente!")
                            st.rerun()
                        else:
                            st.error("Errore nell'eliminazione della riga.")
                    if c_b2.button("❌ No, annulla", use_container_width=True):
                        st.session_state[confirm_key] = False
                        st.rerun()
        else:
            st.info("Nessun record salvato.")

# ---------------------------------------------------------------------------
# LOGICA APP PRINCIPALE
# ---------------------------------------------------------------------------
try:
    check_auth()

    if "pagina" not in st.session_state:
        st.session_state.pagina = "home"

    if st.session_state.pagina == "quadratura_prati":
        render_form_quadratura("Prati")
        st.stop()
    elif st.session_state.pagina == "quadratura_trieste":
        render_form_quadratura("Corso Trieste")
        st.stop()

    dati_raw = fetch_all_data(ID_FOGLIO)

    # 1. LOGO / HEADER
    c_l, c_c, c_r = st.columns([1, 2, 1])
    with c_c:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.title("AQUATIME")

    # BARRA STRUMENTI QUADRATURA CASSA
    st.write("")
    with st.container(border=True):
        st.markdown("💰 **Sezione Quadratura Cassa Giornaliera**")
        cq1, cq2 = st.columns(2)
        if cq1.button("📋 Apri Cassa Prati", use_container_width=True):
            st.session_state.pagina = "quadratura_prati"
            st.rerun()
        if cq2.button("📋 Apri Cassa Corso Trieste", use_container_width=True):
            st.session_state.pagina = "quadratura_trieste"
            st.rerun()
    st.write("")

    # 2. RICERCA E REPORT
    st.divider()
    with st.expander("🔍 **RICERCA ATLETA E REPORT PDF**", expanded=True):
        col1, col2 = st.columns(2)
        n_input = col1.text_input("Filtra Nome", key="src_n").strip()
        c_input = col2.text_input("Filtra Cognome", key="src_c").strip()

        if (n_input or c_input) and dati_raw:
            df_full = get_df_normalizzato(dati_raw)
            res = df_full[
                df_full["Nome"].astype(str).str.contains(n_input, case=False, na=False) &
                df_full["Cognome"].astype(str).str.contains(c_input, case=False, na=False)
            ].copy()

            if not res.empty:
                c_data = get_exact_col(res.columns, "DATA")
                if c_data:
                    res[c_data] = pd.to_datetime(res[c_data], dayfirst=True, errors="coerce")
                    res = res.sort_values(c_data, ascending=False)

                df_view = filtra_privacy(res)
                df_display = df_view.copy()

                if c_data:
                    df_display[c_data] = df_display[c_data].dt.strftime("%d/%m/%Y")

                st.dataframe(df_display, use_container_width=True)

                data_oggi = datetime.now().strftime("%Y%m%d")
                nome_atleta_pulito = f"{n_input}_{c_input}".replace(" ", "_")
                nome_file_pdf = f"Report_{data_oggi}_{nome_atleta_pulito}.pdf"

                pdf_out = generate_pdf(df_view, f"{n_input} {c_input}")
                if pdf_out:
                    st.download_button(
                        label="📥 Scarica Report PDF",
                        data=pdf_out,
                        file_name=nome_file_pdf,
                        mime="application/pdf",
                        use_container_width=True
                    )
            else:
                st.warning("Nessun atleta trovato.")

    # 3. NUOVA SESSIONE
    st.divider()
    st.subheader("📝 Nuova Sessione")

    if "form_id" not in st.session_state:
        st.session_state.form_id = 0
    fid = st.session_state.form_id

    with st.container(border=True):
        f1, f2, f3 = st.columns(3)
        nome_ins    = f1.text_input("Nome *", key=f"n_{fid}")
        cognome_ins = f2.text_input("Cognome *", key=f"c_{fid}")
        sede_ins    = f3.selectbox("Sede *", ["Prati", "Corso Trieste"], index=None, placeholder="Scegli sede...", key=f"s_{fid}")

        st.write("---")
        c1, c2, c3, c4 = st.columns(4)
        data_s = c1.date_input("Data *", value=None, format="DD/MM/YYYY", key=f"d_{fid}")

        dur_sel = c2.selectbox("Sessione *", ["30 min", "45 min", "Altro..."], index=None, key=f"dur_{fid}")
        f_durata = dur_sel
        if dur_sel == "Altro...":
            f_durata = c2.text_input("Specifica Sessione", key=f"dura_{fid}")

        prg_sel = c3.selectbox("Programma *", ["Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."], index=None, key=f"prg_{fid}")
        f_prog = prg_sel
        if prg_sel == "Altro...":
            f_prog = c3.text_input("Specifica Programma", key=f"prga_{fid}")

        liv_sel = c4.selectbox("Livello *", [
            "1-resistenza", "2-resistenza", "3-resistenza",
            "1-variabile", "2-variabile", "3-variabile",
            "4-variabile", "5-variabile", "6-variabile", "Altro..."
        ], index=None, key=f"liv_{fid}")
        f_liv = liv_sel
        if liv_sel == "Altro...":
            f_liv = c4.text_input("Specifica Livello", key=f"liva_{fid}")

        st.write("---")
        f8, f9, f10, f11 = st.columns(4)
        vel       = f8.number_input("Km/h *", min_value=0.0, step=0.1, key=f"v_{fid}")
        dist      = f9.number_input("Km *", min_value=0.0, step=0.1, key=f"dist_{fid}")
        cal       = f10.number_input("Calorie *", min_value=0, key=f"cal_{fid}")
        temp_h2o  = f11.number_input("Temperatura Acqua (°C) *", min_value=0.0, value=0.00, step=0.5, key=f"temp_{fid}")

        st.write("---")
        note_ins_val = st.text_input("Note Sessione (Opzionale)", key=f"note_ins_{fid}")

        _, col_btn, _ = st.columns([2, 1, 2])
        if col_btn.button("Salva Sessione", use_container_width=True):
            if nome_ins and cognome_ins and sede_ins and data_s and f_durata and f_prog and f_liv:
                try:
                    sheet = get_sheet()
                    riga = [
                        sanifica(f"{nome_ins} {cognome_ins}"),
                        sanifica(nome_ins),
                        sanifica(cognome_ins),
                        0, "",  # Campi saltati/vuoti intermedi
                        data_s.strftime("%d/%m/%Y"),
                        sanifica(f_durata),
                        sanifica(f_prog),
                        sanifica(f_liv),
                        vel,
                        dist,
                        cal,
                        sede_ins,
                        0, 0, 0, # Frequenza cardiaca / FC / Altro fittizio
                        sanifica(note_ins_val),
                        temp_h2o
                    ]
                    ok = _retry(sheet.append_row, riga)
                    if ok:
                        invalida_df_cache()
                        fetch_all_data.clear()
                        st.session_state.form_id += 1
                        st.success("Salvato correttamente!")
                        st.rerun()
                    else:
                        st.error("Errore nel salvataggio. Riprova.")
                except Exception as e:
                    st.error(f"Errore durante il salvataggio: {e}")
            else:
                st.error("Compila i campi obbligatori (*)")

    # 4. ARCHIVIO E CANCELLAZIONE
    st.divider()
    st.subheader("📊 Archivio Recente (30gg)")
    if dati_raw:
        df_glob = get_df_normalizzato(dati_raw)
        c_data_g = get_exact_col(df_glob.columns, "DATA")
        if c_data_g:
            df_glob[c_data_g] = pd.to_datetime(df_glob[c_data_g], dayfirst=True, errors="coerce")
            limite = datetime.now() - timedelta(days=30)
            df_recenti = df_glob[df_glob[c_data_g] >= limite].copy().sort_values(c_data_g, ascending=False)

            if not df_recenti.empty:
                df_rec_disp = filtra_privacy(df_recenti)
                df_rec_disp[c_data_g] = df_rec_disp[c_data_g].dt.strftime("%d/%m/%Y")
                st.dataframe(df_rec_disp, use_container_width=True)

                with st.expander("🗑️ Cancella una riga dall'archivio"):
                    opzioni = []
                    for _, r in df_recenti.iterrows():
                        label = f"{r[c_data_g].strftime('%d/%m/%Y')} - {r['Nome']} {r['Cognome']}"
                        opzioni.append({
                            "label": label,
                            "row_number": r["GOOGLE_SHEET_ROW"]
                        })

                    scelta_idx = st.selectbox(
                        "Seleziona la sessione da eliminare:",
                        range(len(opzioni)),
                        format_func=lambda i: opzioni[i]["label"],
                        index=None,
                        key="sel_cancella"
                    )

                    if scelta_idx is not None:
                        scelta = opzioni[scelta_idx]
                        st.warning(
                            f"⚠️ Stai per eliminare: **{scelta['label']}**. "
                            "Questa azione è irreversibile."
                        )
                        col_si, col_no = st.columns(2)
                        if col_si.button("✅ Sì, elimina", use_container_width=True):
                            with st.spinner("Eliminazione in corso..."):
                                sheet = get_sheet()
                                ok = _retry(sheet.delete_rows, scelta["row_number"])
                                if ok:
                                    del st.session_state["sel_cancella"]
                                    invalida_df_cache()
                                    fetch_all_data.clear()
                                    st.rerun()
                                else:
                                    st.error("❌ Eliminazione fallita.")
                        if col_no.button("❌ Annulla", use_container_width=True):
                            del st.session_state["sel_cancella"]
                            st.rerun()

except Exception as e:
    logger.error("Errore generale: %s", e)
    st.error(f"Errore generale: {e}")
