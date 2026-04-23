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
    """
    Restituisce il tab 'Quadrature'. Se non esiste lo crea con le intestazioni.
    Non cachato perché ha side-effect (creazione tab).
    """
    spreadsheet = get_gspread_client().open_by_key(ID_FOGLIO)
    try:
        ws = spreadsheet.worksheet(QUADRATURE_SHEET_NAME)
        # Verifica che le intestazioni esistano
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
    """
    Recupera l'ultimo Saldo_Finale dal tab Quadrature per la sede indicata.
    Restituisce 0.0 se non ci sono record precedenti.
    """
    try:
        ws = get_or_create_quadrature_sheet()
        records = ws.get_all_records()
        records_sede = [r for r in records if str(r.get("Sede", "")).strip() == sede]
        if records_sede:
            return force_numeric(records_sede[-1].get("Saldo_Finale", 0))
    except Exception as e:
        logger.error("Errore recupero saldo iniziale: %s", e)
    return 0.0

# ---------------------------------------------------------------------------
# UTILITY — WORKOUT
# ---------------------------------------------------------------------------
def force_numeric(val) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


def normalizza_numerici(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        col_up = str(col).upper().strip()
        is_numeric_col = (
            COL_KEYWORDS["KMH"](col_up)
            or COL_KEYWORDS["KM"](col_up)
            or COL_KEYWORDS["CALORIE"](col_up)
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
    """
    Replica le formule Excel del FOGLIO_CASSA_GIORNALIERO:
      U25  = SUM(A25:T27)  → Tot_Scontrini
      W33  = SUM(A33:V35)  → Tot_Fatture
      AA41 = SUM(A41:Z43)  → Tot_Generale (= Tot_Scontrini + Tot_Fatture)
      I60  = G25+G33       → Incasso_Contanti
      I73  = I58+I60-I62-I64-I66-I68-I70 → Saldo_Finale
    """
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

    # O15 = F15+K15 = Tot_Generale + Sospeso
    d["Sospeso_Booker"] = round(d["Tot_Generale"] + d.get("Sospeso", 0.0), 2)

    # E52 = A52+C52 → Totale Altri Servizi
    d["AS_Totale"] = round(d.get("AS_Altro", 0.0) + d.get("AS_Aquatime", 0.0), 2)

    # Incasso contanti = contanti scontrini + contanti fatture (cella I60 = G25+G33)
    d["Incasso_Contanti"] = round(
        d.get("Sc_Contanti", 0.0) + d.get("Ft_Contanti", 0.0), 2
    )

    # Saldo finale = I73 = I58 + I60 - I62 - I64 - I66 - I68 - I70
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


def _nv(val) -> float:
    """Converte None (campo vuoto) in 0.0 per i calcoli live nel form."""
    return 0.0 if val is None else float(val)


def _fmt(val) -> str:
    """Formatta un valore numerico come stringa Euro per il PDF."""
    try:
        f = float(val)
        return f"EUR {f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "€ 0,00"

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

        km_vals = df_atleta[c_km].apply(force_numeric)        if c_km  else pd.Series([0.0])
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

        col_widths = [25, 45, 40, 20, 20, 25]
        headers    = ["Data", "Programma", "Livello", "Km", "Km/h", "Calorie"]
        pdf.set_font("helvetica", "B", 9)
        pdf.set_fill_color(0, 80, 158)
        pdf.set_text_color(255, 255, 255)
        for w, h in zip(col_widths, headers):
            pdf.cell(w, 8, h, 1, 0, "C", True)
        pdf.ln()

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

            pdf.cell(col_widths[0], 7, solo_data,                                    1, 0, "C")
            pdf.cell(col_widths[1], 7, str(row.get(c_prog, ""))[:MAX_PDF_PROG_LEN], 1, 0, "L")
            pdf.cell(col_widths[2], 7, str(row.get(c_liv,  ""))[:MAX_PDF_LIV_LEN],  1, 0, "L")
            pdf.cell(col_widths[3], 7, str(row.get(c_km,   "0")),                   1, 0, "C")
            pdf.cell(col_widths[4], 7, str(row.get(c_kmh,  "0")),                   1, 0, "C")
            pdf.cell(col_widths[5], 7, str(row.get(c_cal,  "0")),                   1, 1, "C")

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
    """
    Genera il PDF della quadratura cassa giornaliera su una pagina A4.
    Layout a due colonne affiancate per Scontrini e Fatture,
    seguita dalla sezione Saldo Cassa.
    """
    try:
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()

        BLUE  = (0, 80, 158)
        LGRAY = (235, 235, 235)
        DGRAY = (180, 180, 180)
        BLACK = (0, 0, 0)
        WHITE = (255, 255, 255)

        LM = 8    # left margin
        PW = 194  # page width usable (210 - 2*8)
        CW = 95   # column width for left/right panels

        # ── HEADER ─────────────────────────────────────────────────────────
        pdf.set_fill_color(*BLUE)
        pdf.rect(0, 0, 210, 18, "F")
        pdf.set_text_color(*WHITE)
        pdf.set_font("helvetica", "B", 14)
        pdf.set_xy(LM, 3)
        pdf.cell(PW, 7, "AQUATIME ROMA - QUADRATURA CASSA GIORNALIERA", align="C")
        pdf.set_font("helvetica", "B", 11)
        pdf.set_xy(LM, 11)
        pdf.cell(PW, 5, f"SEDE: {d.get('Sede','').upper()}", align="C")

        # ── INFO ROW ───────────────────────────────────────────────────────
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

        # ── Helper: sezione bicolonna ───────────────────────────────────────
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

        # ── SCONTRINI FISCALI (colonna sinistra) ───────────────────────────
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
            (f"Altro ({d.get('Sc_Altro_Desc','')[:12]})",
                            d.get("Sc_Altro",       0.0)),
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
            (f"Altro ({d.get('Ft_Altro_Desc','')[:12]})",
                            d.get("Ft_Altro",       0.0)),
        ]

        max_rows = max(len(scontrini_rows), len(fatture_rows))
        for i in range(max_rows):
            if i < len(scontrini_rows):
                payment_row(scontrini_rows[i][0], scontrini_rows[i][1], x_left, y_cur)
            if i < len(fatture_rows):
                payment_row(fatture_rows[i][0], fatture_rows[i][1], x_right, y_cur)
            y_cur += 5.5

        # Totali sezione
        payment_row("TOTALE SCONTRINI", d["Tot_Scontrini"], x_left,  y_cur, fill=True)
        payment_row("TOTALE FATTURE",   d["Tot_Fatture"],   x_right, y_cur, fill=True)
        y_cur += 5.5 + 4

        # ── TOTALE GENERALE ────────────────────────────────────────────────
        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*BLUE)
        pdf.set_text_color(*WHITE)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(130, 8, "TOTALE GENERALE (Scontrini + Fatture)", 1, 0, "L", True)
        pdf.cell(PW - 130, 8, _fmt(d["Tot_Generale"]), 1, 1, "R", True)
        pdf.set_text_color(*BLACK)
        y_cur = pdf.get_y() + 3

        # ── SOSPESO E RICONCILIAZIONE BOOKER ───────────────────────────────
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

        # ── ALTRI SERVIZI / FATTURE ─────────────────────────────────────────
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

        # ── SALDO CASSA CONTANTI ───────────────────────────────────────────
        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*BLUE)
        pdf.set_text_color(*WHITE)
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(PW, 6, "SALDO CASSA CONTANTI", 1, 1, "C", True)
        pdf.set_text_color(*BLACK)
        y_cur = pdf.get_y()

        LW_SALDO = 110  # label width
        VW_SALDO = PW - LW_SALDO  # value width

        def saldo_row(label: str, val, bold_val: bool = False,
                      fill_color=None, text_color=BLACK):
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
        saldo_row(note1,                                   d.get("Pag1",              0.0))
        saldo_row(note2,                                   d.get("Pag2",              0.0))
        saldo_row(note3,                                   d.get("Pag3",              0.0))
        saldo_row("(-) Versamento in Banca",               d.get("Versamento_Banca",  0.0))
        saldo_row("(-) Prelievo Amministratore",           d.get("Prelievo_Admin",    0.0))

        # Saldo Finale — riga evidenziata
        pdf.set_xy(LM, y_cur)
        pdf.set_fill_color(*BLUE)
        pdf.set_text_color(*WHITE)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(LW_SALDO, 8, "SALDO FINALE CASSA CONTANTI", 1, 0, "L", True)
        pdf.cell(VW_SALDO, 8, _fmt(d["Saldo_Finale"]), 1, 1, "R", True)

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
    """Renderizza il form di quadratura cassa per la sede indicata."""

    # ── Bottone torna alla home ─────────────────────────────────────────────
    if st.button("← Torna alla Home"):
        st.session_state.pagina = "home"
        st.rerun()

    st.subheader(f"📋 Quadratura Cassa — {sede}")

    # form_id per reset dopo salvataggio
    if "qfid" not in st.session_state:
        st.session_state.qfid = 0
    qfid = st.session_state.qfid

    # Saldo iniziale pre-caricato dal giorno precedente
    if f"saldo_init_loaded_{sede}_{qfid}" not in st.session_state:
        st.session_state[f"saldo_init_loaded_{sede}_{qfid}"] = get_last_saldo_iniziale(sede)

    saldo_precedente = st.session_state[f"saldo_init_loaded_{sede}_{qfid}"]

    with st.container(border=True):

        # ── INTESTAZIONE ─────────────────────────────────────────────────
        st.markdown("**📅 Intestazione**")
        c1, c2 = st.columns(2)
        data_q   = c1.date_input("Data *", value=datetime.today(), format="DD/MM/YYYY",
                                 key=f"qdata_{qfid}")
        OPERATORI = [
            "Barbara Iorio", "Barbara Pasqualini", "Daniela Bissieres",
            "Jacopo Vendetti", "Stefano Lampis", "Sofia Amore",
            "Gianluca Nania", "Altro..."
        ]
        op_sel = c2.selectbox("Operatore *", OPERATORI, index=None,
                              placeholder="Scegli operatore...", key=f"qop_sel_{qfid}")
        operatore = ""
        if op_sel == "Altro...":
            operatore = st.text_input("Specificare operatore *",
                                      key=f"qop_txt_{qfid}", max_chars=MAX_INPUT_LEN)
        elif op_sel:
            operatore = op_sel

        st.divider()

        # ── SCONTRINI FISCALI ─────────────────────────────────────────────
        st.markdown("**🧾 Scontrini Fiscali**")
        cs1, cs2, cs3, cs4, cs5 = st.columns(5)
        sc_bancomat  = cs1.number_input("Bancomat",   min_value=0.0, step=0.01, value=None, key=f"sc_bk_{qfid}")
        sc_visa      = cs2.number_input("Visa",       min_value=0.0, step=0.01, value=None, key=f"sc_vs_{qfid}")
        sc_master    = cs3.number_input("Mastercard", min_value=0.0, step=0.01, value=None, key=f"sc_mc_{qfid}")
        sc_contanti  = cs4.number_input("Contanti",   min_value=0.0, step=0.01, value=None, key=f"sc_ct_{qfid}")
        sc_bonifico  = cs5.number_input("Bonifico",   min_value=0.0, step=0.01, value=None, key=f"sc_bn_{qfid}")

        cs6, cs7, cs8, cs9, cs10 = st.columns(5)
        sc_assegno   = cs6.number_input("Assegno",   min_value=0.0, step=0.01, value=None, key=f"sc_as_{qfid}")
        sc_groupon   = cs7.number_input("Groupon",   min_value=0.0, step=0.01, value=None, key=f"sc_gp_{qfid}")
        sc_gympass   = cs8.number_input("Gympass",   min_value=0.0, step=0.01, value=None, key=f"sc_gym_{qfid}")
        sc_amex      = cs9.number_input("Amex",      min_value=0.0, step=0.01, value=None, key=f"sc_amx_{qfid}")
        sc_altro     = cs10.number_input("Altro",    min_value=0.0, step=0.01, value=None, key=f"sc_alt_{qfid}")
        sc_altro_desc = st.text_input("Specificare Altro Scontrini",
                                      key=f"sc_altd_{qfid}", max_chars=50)

        tot_sc = round(_nv(sc_bancomat)+_nv(sc_visa)+_nv(sc_master)+_nv(sc_contanti)+_nv(sc_bonifico)+
                       _nv(sc_assegno)+_nv(sc_groupon)+_nv(sc_gympass)+_nv(sc_amex)+_nv(sc_altro), 2)
        st.info(f"**Totale Scontrini: {_fmt(tot_sc)}**")

        st.divider()

        # ── FATTURE ───────────────────────────────────────────────────────
        st.markdown("**📄 Fatture**")
        cf1, cf2, cf3, cf4, cf5 = st.columns(5)
        ft_bancomat  = cf1.number_input("Bancomat",    min_value=0.0, step=0.01, value=None, key=f"ft_bk_{qfid}")
        ft_visa      = cf2.number_input("Visa",        min_value=0.0, step=0.01, value=None, key=f"ft_vs_{qfid}")
        ft_master    = cf3.number_input("Mastercard",  min_value=0.0, step=0.01, value=None, key=f"ft_mc_{qfid}")
        ft_contanti  = cf4.number_input("Contanti",    min_value=0.0, step=0.01, value=None, key=f"ft_ct_{qfid}")
        ft_bonifico  = cf5.number_input("Bonifico",    min_value=0.0, step=0.01, value=None, key=f"ft_bn_{qfid}")

        cf6, cf7, cf8, cf9, cf10, cf11 = st.columns(6)
        ft_assegno   = cf6.number_input("Assegno",    min_value=0.0, step=0.01, value=None, key=f"ft_as_{qfid}")
        ft_groupon   = cf7.number_input("Groupon",    min_value=0.0, step=0.01, value=None, key=f"ft_gp_{qfid}")
        ft_fitprime  = cf8.number_input("Fitprime",   min_value=0.0, step=0.01, value=None, key=f"ft_fp_{qfid}")
        ft_amex      = cf9.number_input("Amex",       min_value=0.0, step=0.01, value=None, key=f"ft_amx_{qfid}")
        ft_aquatime  = cf10.number_input("Aquatime",  min_value=0.0, step=0.01, value=None, key=f"ft_aq_{qfid}")
        ft_altro     = cf11.number_input("Altro",     min_value=0.0, step=0.01, value=None, key=f"ft_alt_{qfid}")
        ft_altro_desc = st.text_input("Specificare Altro Fatture",
                                      key=f"ft_altd_{qfid}", max_chars=50)

        tot_ft = round(_nv(ft_bancomat)+_nv(ft_visa)+_nv(ft_master)+_nv(ft_contanti)+_nv(ft_bonifico)+
                       _nv(ft_assegno)+_nv(ft_groupon)+_nv(ft_fitprime)+_nv(ft_amex)+_nv(ft_aquatime)+_nv(ft_altro), 2)
        st.info(f"**Totale Fatture: {_fmt(tot_ft)}**")

        st.divider()

        # ── SOSPESO E RICONCILIAZIONE BOOKER ─────────────────────────────
        st.markdown("**🔄 Riconciliazione Booker**")
        tot_gen_live = round(tot_sc + tot_ft, 2)
        rb1, rb2 = st.columns(2)
        sospeso = rb1.number_input(
            "Sospeso (K15)",
            min_value=0.0, step=0.01, value=None, key=f"q_sosp_{qfid}",
            help="Pagamenti sospesi/differiti da riconciliare con il sistema Booker"
        )
        sospeso_booker = round(tot_gen_live + _nv(sospeso), 2)
        rb2.metric(
            "Sospeso + Totale Booker (O15)",
            _fmt(sospeso_booker),
            help="Calcolato: Totale Generale + Sospeso (formula O15 = F15+K15)"
        )

        st.divider()

        # ── ALTRI SERVIZI / FATTURE ───────────────────────────────────────
        st.markdown("**🛎️ Altri Servizi / Fatture**")
        as1, as2, as3 = st.columns(3)
        as_altro    = as1.number_input("Altro",    min_value=0.0, step=0.01, value=None, key=f"q_asa_{qfid}")
        as_aquatime = as2.number_input("Aquatime", min_value=0.0, step=0.01, value=None, key=f"q_asq_{qfid}")
        as_totale   = round(_nv(as_altro) + _nv(as_aquatime), 2)
        as3.metric("Totale Altri Servizi", _fmt(as_totale))

        st.divider()

        # ── SALDO CASSA CONTANTI ──────────────────────────────────────────
        st.markdown("**💵 Saldo Cassa Contanti**")

        cs_col1, cs_col2 = st.columns(2)
        saldo_iniziale = cs_col1.number_input(
            "Saldo Iniziale Cassa (dal giorno precedente) *",
            value=float(saldo_precedente),
            min_value=0.0, step=0.01,
            key=f"q_siniz_{qfid}",
            help="Pre-compilato con il saldo finale del giorno precedente. Modificabile."
        )

        incasso_contanti = round(_nv(sc_contanti) + _nv(ft_contanti), 2)
        cs_col2.metric("Incasso Contanti del giorno", _fmt(incasso_contanti),
                       help="Calcolato automaticamente: Contanti Scontrini + Contanti Fatture")

        cp1, cp2, cp3 = st.columns(3)
        pag1 = cp1.number_input("Pagamento 1 (€)", min_value=0.0, step=0.01, value=None, key=f"q_p1_{qfid}")
        pag2 = cp2.number_input("Pagamento 2 (€)", min_value=0.0, step=0.01, value=None, key=f"q_p2_{qfid}")
        pag3 = cp3.number_input("Pagamento 3 (€)", min_value=0.0, step=0.01, value=None, key=f"q_p3_{qfid}")

        cn1, cn2, cn3 = st.columns(3)
        note_pag1 = cn1.text_input("Descrizione Pag. 1", key=f"q_n1_{qfid}", max_chars=50)
        note_pag2 = cn2.text_input("Descrizione Pag. 2", key=f"q_n2_{qfid}", max_chars=50)
        note_pag3 = cn3.text_input("Descrizione Pag. 3", key=f"q_n3_{qfid}", max_chars=50)

        cv1, cv2 = st.columns(2)
        versamento = cv1.number_input("Versamento in Banca (€)", min_value=0.0, step=0.01, value=None,
                                      key=f"q_vb_{qfid}")
        prelievo   = cv2.number_input("Prelievo Amministratore (€)", min_value=0.0, step=0.01, value=None,
                                      key=f"q_pa_{qfid}")

        # Riepilogo calcolato in tempo reale
        saldo_finale = round(_nv(saldo_iniziale) + incasso_contanti
                             - _nv(pag1) - _nv(pag2) - _nv(pag3) - _nv(versamento) - _nv(prelievo), 2)
        tot_gen      = round(tot_sc + tot_ft, 2)

        st.divider()
        r1, r2, r3 = st.columns(3)
        r1.metric("Totale Generale",     _fmt(tot_gen))
        r2.metric("Incasso Contanti",     _fmt(incasso_contanti))
        r3.metric("💰 Saldo Finale Cassa", _fmt(saldo_finale))

        # ── PULSANTE SALVA ────────────────────────────────────────────────
        _, col_btn, _ = st.columns([2, 1, 2])
        if col_btn.button("💾 Salva e genera PDF", use_container_width=True):

            errori = []
            if not op_sel:
                errori.append("Operatore (nessuna selezione)")
            elif op_sel == "Altro..." and not operatore:
                errori.append("Operatore (hai scelto 'Altro...' ma non hai specificato il nome)")
            if not data_q:    errori.append("Data")

            if errori:
                st.error(f"Compila i campi obbligatori: {', '.join(errori)}")
            else:
                # Raccogli tutti i dati
                inp = {
                    "Data":      data_q.strftime("%d/%m/%Y"),
                    "Sede":      sede,
                    "Operatore": sanifica(operatore),
                    # Scontrini
                    "Sc_Bancomat":   _nv(sc_bancomat),  "Sc_Visa":     _nv(sc_visa),
                    "Sc_Mastercard": _nv(sc_master),    "Sc_Contanti": _nv(sc_contanti),
                    "Sc_Bonifico":   _nv(sc_bonifico),  "Sc_Assegno":  _nv(sc_assegno),
                    "Sc_Groupon":    _nv(sc_groupon),   "Sc_Gympass":  _nv(sc_gympass),
                    "Sc_Amex":       _nv(sc_amex),      "Sc_Altro":    _nv(sc_altro),
                    "Sc_Altro_Desc": sanifica(sc_altro_desc),
                    # Fatture
                    "Ft_Bancomat":   _nv(ft_bancomat),  "Ft_Visa":     _nv(ft_visa),
                    "Ft_Mastercard": _nv(ft_master),    "Ft_Contanti": _nv(ft_contanti),
                    "Ft_Bonifico":   _nv(ft_bonifico),  "Ft_Assegno":  _nv(ft_assegno),
                    "Ft_Groupon":    _nv(ft_groupon),   "Ft_Fitprime": _nv(ft_fitprime),
                    "Ft_Amex":       _nv(ft_amex),      "Ft_Aquatime": _nv(ft_aquatime),
                    "Ft_Altro":      _nv(ft_altro),     "Ft_Altro_Desc": sanifica(ft_altro_desc),
                    # Sospeso
                    "Sospeso":       _nv(sospeso),
                    # Altri servizi
                    "AS_Altro":      _nv(as_altro),
                    "AS_Aquatime":   _nv(as_aquatime),
                    # Saldo
                    "Saldo_Iniziale": _nv(saldo_iniziale),
                    "Pag1": _nv(pag1), "Note_Pag1": sanifica(note_pag1),
                    "Pag2": _nv(pag2), "Note_Pag2": sanifica(note_pag2),
                    "Pag3": _nv(pag3), "Note_Pag3": sanifica(note_pag3),
                    "Versamento_Banca": _nv(versamento),
                    "Prelievo_Admin":   _nv(prelievo),
                }
                dati = calcola_quadratura(inp)

                with st.spinner("Salvataggio e generazione PDF in corso..."):
                    try:
                        # Salva nel Google Sheet
                        ws  = get_or_create_quadrature_sheet()
                        riga = [dati.get(col, "") for col in QUADRATURE_HEADERS]
                        ok = _retry(ws.append_row, riga)

                        if ok:
                            # Genera PDF
                            pdf_bytes = genera_pdf_quadratura(dati)
                            nome_file = (
                                f"{sede.replace(' ', '_')}_"
                                f"{data_q.strftime('%d-%m-%Y')}.pdf"
                            )

                            st.success("✅ Dati salvati correttamente!")

                            if pdf_bytes:
                                st.download_button(
                                    "📥 Scarica PDF Quadratura",
                                    pdf_bytes, nome_file,
                                    "application/pdf",
                                    use_container_width=True
                                )

                            # Reset form
                            st.session_state.qfid += 1
                            # Rimuovi saldo cached per forzare ricarico
                            chiave_saldo = f"saldo_init_loaded_{sede}_{qfid}"
                            if chiave_saldo in st.session_state:
                                del st.session_state[chiave_saldo]
                        else:
                            st.error("❌ Salvataggio fallito. Riprova.")
                    except Exception as e:
                        logger.error("Errore salvataggio quadratura: %s", e)
                        st.error(f"Errore: {e}")


# ===========================================================================
# APP PRINCIPALE
# ===========================================================================
check_auth()

# Inizializza navigazione
if "pagina" not in st.session_state:
    st.session_state.pagina = "home"

# ── ROUTING ────────────────────────────────────────────────────────────────
if st.session_state.pagina in ("quad_Prati", "quad_Corso Trieste"):
    sede_attiva = "Prati" if st.session_state.pagina == "quad_Prati" else "Corso Trieste"
    render_form_quadratura(sede_attiva)
    st.stop()

# ── HOME PAGE ──────────────────────────────────────────────────────────────
try:
    try:
        dati_raw = fetch_all_data(ID_FOGLIO)
    except Exception as e:
        logger.error("Errore fetch dati: %s", e)
        st.error(f"Impossibile caricare i dati dal foglio: {e}")
        st.stop()

    df_norm = get_df_normalizzato(dati_raw)

    # ── 1. LOGO ──────────────────────────────────────────────────────────
    _, c_c, _ = st.columns([1, 2, 1])
    with c_c:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.title("AQUATIME")

    # ── 2. PULSANTI QUADRATURA CASSA ─────────────────────────────────────
    st.divider()
    st.subheader("📊 Quadratura Cassa Giornaliera")
    qc1, qc2 = st.columns(2)
    if qc1.button("🏛️ Quadratura Prati",        use_container_width=True):
        st.session_state.pagina = "quad_Prati"
        st.rerun()
    if qc2.button("🏛️ Quadratura Corso Trieste", use_container_width=True):
        st.session_state.pagina = "quad_Corso Trieste"
        st.rerun()

    # ── 3. RICERCA E REPORT PDF ──────────────────────────────────────────
    st.divider()
    with st.expander("🔍 **RICERCA ATLETA E REPORT PDF**", expanded=True):
        col1, col2 = st.columns(2)
        n_input = col1.text_input("Filtra Nome",    key="src_n", max_chars=MAX_INPUT_LEN)
        c_input = col2.text_input("Filtra Cognome", key="src_c", max_chars=MAX_INPUT_LEN)

        if (n_input or c_input) and dati_raw:
            mask = (
                df_norm["Nome"].astype(str).str.contains(n_input, case=False, na=False, regex=False)
                & df_norm["Cognome"].astype(str).str.contains(c_input, case=False, na=False, regex=False)
            )
            res = df_norm[mask].copy()

            if not res.empty:
                c_data_col = get_exact_col(res.columns, "DATA")
                if c_data_col:
                    res[c_data_col] = pd.to_datetime(res[c_data_col], dayfirst=True, errors="coerce")
                    res = res.sort_values(c_data_col, ascending=False)

                df_view    = filtra_privacy(res)
                df_display = df_view.copy()
                if c_data_col and c_data_col in df_display.columns:
                    df_display[c_data_col] = df_display[c_data_col].dt.strftime("%d/%m/%Y")

                st.dataframe(df_display, use_container_width=True)

                nome_file_pdf = f"Report_{datetime.now():%d%m%Y}_{n_input}_{c_input}.pdf".replace(" ", "_")
                pdf_out = generate_pdf(df_view, f"{n_input} {c_input}")
                if pdf_out:
                    st.download_button(
                        "📥 Scarica Report PDF", pdf_out,
                        nome_file_pdf, "application/pdf",
                        use_container_width=True
                    )
            else:
                st.warning("Nessun atleta trovato.")

    # ── 4. NUOVA SESSIONE WORKOUT ────────────────────────────────────────
    st.divider()
    st.subheader("📝 Nuova Sessione")

    if "form_id" not in st.session_state:
        st.session_state.form_id = 0
    fid = st.session_state.form_id

    with st.container(border=True):
        f1, f2, f3 = st.columns(3)
        nome_ins    = f1.text_input("Nome *",    key=f"n_{fid}", max_chars=MAX_INPUT_LEN)
        cognome_ins = f2.text_input("Cognome *", key=f"c_{fid}", max_chars=MAX_INPUT_LEN)
        sede_ins    = f3.selectbox(
            "Sede *", ["Prati", "Corso Trieste"],
            index=None, placeholder="Scegli sede...", key=f"s_{fid}"
        )

        st.write("---")
        c1, c2, c3, c4 = st.columns(4)
        data_s = c1.date_input("Data *", value=None, format="DD/MM/YYYY", key=f"d_{fid}")

        dur_sel  = c2.selectbox(
            "Sessione *", ["30 min", "45 min", "Altro..."],
            index=None, key=f"dur_{fid}"
        )
        f_durata = c2.text_input(
            "Specifica Sessione", key=f"dura_{fid}", max_chars=MAX_INPUT_LEN
        ) if dur_sel == "Altro..." else dur_sel

        prg_sel = c3.selectbox(
            "Programma *", ["Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."],
            index=None, key=f"prg_{fid}"
        )
        f_prog  = c3.text_input(
            "Specifica Programma", key=f"prga_{fid}", max_chars=MAX_INPUT_LEN
        ) if prg_sel == "Altro..." else prg_sel

        liv_sel = c4.selectbox(
            "Livello *",
            ["1-resistenza","2-resistenza","3-resistenza",
             "1-variabile","2-variabile","3-variabile",
             "4-variabile","5-variabile","6-variabile","Altro..."],
            index=None, key=f"liv_{fid}"
        )
        f_liv   = c4.text_input(
            "Specifica Livello", key=f"liva_{fid}", max_chars=MAX_INPUT_LEN
        ) if liv_sel == "Altro..." else liv_sel

        st.write("---")
        f8, f9, f10 = st.columns(3)
        vel  = f8.number_input("Km/h *",     min_value=0.0, step=0.1, key=f"v_{fid}")
        dist = f9.number_input("Km *",       min_value=0.0, step=0.1, key=f"dist_{fid}")
        cal  = f10.number_input("Calorie *", min_value=0,              key=f"cal_{fid}")

        _, col_btn, _ = st.columns([2, 1, 2])
        if col_btn.button("💾 Salva Sessione", use_container_width=True):

            errori = []
            if not nome_ins:    errori.append("Nome")
            if not cognome_ins: errori.append("Cognome")
            if not sede_ins:    errori.append("Sede")
            if not data_s:      errori.append("Data")
            if not dur_sel:
                errori.append("Sessione (nessuna selezione)")
            elif dur_sel == "Altro..." and not f_durata:
                errori.append("Sessione (hai scelto 'Altro...' ma non hai specificato il valore)")
            if not prg_sel:
                errori.append("Programma (nessuna selezione)")
            elif prg_sel == "Altro..." and not f_prog:
                errori.append("Programma (hai scelto 'Altro...' ma non hai specificato il valore)")
            if not liv_sel:
                errori.append("Livello (nessuna selezione)")
            elif liv_sel == "Altro..." and not f_liv:
                errori.append("Livello (hai scelto 'Altro...' ma non hai specificato il valore)")
            if vel == 0.0 and dist == 0.0 and cal == 0:
                errori.append("almeno un valore tra Km/h, Km, Calorie deve essere > 0")

            if errori:
                st.error(f"Compila i campi obbligatori: {', '.join(errori)}")
            else:
                with st.spinner("Salvataggio in corso..."):
                    try:
                        sheet = get_sheet()
                        riga  = [
                            sanifica(f"{nome_ins} {cognome_ins}"),
                            sanifica(nome_ins),
                            sanifica(cognome_ins),
                            0, "",
                            data_s.strftime("%d/%m/%Y"),
                            sanifica(f_durata),
                            sanifica(f_prog),
                            sanifica(f_liv),
                            vel, dist, cal,
                            sanifica(sede_ins),
                            0, 0, 0
                        ]
                        ok = _retry(sheet.append_row, riga)
                        if ok:
                            st.cache_data.clear()
                            invalida_df_cache()
                            st.session_state.form_id += 1
                            st.success("✅ Sessione salvata correttamente!")
                            st.rerun()
                        else:
                            st.error("❌ Salvataggio fallito dopo 3 tentativi.")
                    except Exception as e:
                        logger.error("Errore salvataggio: %s", e)
                        st.error(f"Errore durante il salvataggio: {e}")

    # ── 5. ARCHIVIO RECENTE E CANCELLAZIONE ─────────────────────────────
    st.divider()
    st.subheader("📊 Archivio Recente (30gg)")

    if dati_raw:
        c_data_g = get_exact_col(df_norm.columns, "DATA")

        if c_data_g:
            df_glob = df_norm.copy()
            df_glob[c_data_g] = pd.to_datetime(df_glob[c_data_g], dayfirst=True, errors="coerce")
            limite     = datetime.now() - timedelta(days=30)
            df_recenti = df_glob[df_glob[c_data_g] >= limite].copy().sort_values(c_data_g, ascending=False)

            if not df_recenti.empty:
                df_rec_disp = filtra_privacy(df_recenti).copy()
                df_rec_disp[c_data_g] = df_rec_disp[c_data_g].dt.strftime("%d/%m/%Y")
                st.dataframe(df_rec_disp, use_container_width=True)

                with st.expander("🗑️ Cancella una riga dall'archivio"):
                    opzioni = [
                        {
                            "label":      f"{r[c_data_g].strftime('%d/%m/%Y')} — {r['Nome']} {r['Cognome']}",
                            "row_number":  r["GOOGLE_SHEET_ROW"],
                        }
                        for _, r in df_recenti.iterrows()
                    ]

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
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("❌ Eliminazione fallita.")
                        if col_no.button("❌ Annulla", use_container_width=True):
                            del st.session_state["sel_cancella"]
                            st.rerun()

except Exception as e:
    logger.error("Errore generale: %s", e)
    st.error(f"Errore generale: {e}")
