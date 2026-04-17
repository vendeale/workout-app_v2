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
# COSTANTI
# ---------------------------------------------------------------------------
ID_FOGLIO = st.secrets["ID_FOGLIO"]

COLONNE_NASCOSTE   = ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"]
GOOGLE_SHEET_OFFSET = 2   # riga 1 = intestazione → i dati iniziano alla riga 2
CACHE_TTL           = 600  # secondi
MAX_PDF_PROG_LEN    = 22
MAX_PDF_LIV_LEN     = 20

# Mapping per get_exact_col: chiave → funzione che riceve il nome colonna in UPPERCASE
COL_KEYWORDS: dict = {
    "KMH":      lambda c: "KM/H" in c or "VELOCIT" in c,
    "KM":       lambda c: ("KM" in c and "KM/H" not in c and "VELOCIT" not in c) or "DISTANZA" in c,
    "DATA":     lambda c: "DATA" in c and "NASCITA" not in c,
    "CALORIE":  lambda c: "CAL" in c or "KCAL" in c,
    "PROGRAMMA":lambda c: "PROGR" in c,
    "LIVELLO":  lambda c: "LIV" in c,
}

# ---------------------------------------------------------------------------
# AUTENTICAZIONE OPZIONALE
# ---------------------------------------------------------------------------
def check_auth() -> None:
    """
    Attiva la password SOLO se 'app_password' è presente in st.secrets.
    Se non è configurata, l'app rimane accessibile come prima.
    Per attivarla basta aggiungere nel tuo secrets.toml:
        app_password = "la-tua-password"
    """
    if "app_password" not in st.secrets:
        return  # nessuna password configurata → accesso libero

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
# ACCESSO AI DATI
# ---------------------------------------------------------------------------
@st.cache_resource
def get_gspread_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scope
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=CACHE_TTL)
def fetch_all_data(id_foglio: str) -> list[dict]:
    try:
        client = get_gspread_client()
        sheet  = client.open_by_key(id_foglio).sheet1
        data   = sheet.get_all_records()
        result = []
        for i, row in enumerate(data):
            clean = {str(k).strip(): v for k, v in row.items()}
            clean["GOOGLE_SHEET_ROW"] = i + GOOGLE_SHEET_OFFSET
            if clean.get("Nome") and str(clean["Nome"]).strip():
                result.append(clean)
        return result
    except Exception as e:
        logger.error("Errore fetch dati: %s", e)
        st.error(f"Impossibile caricare i dati dal foglio: {e}")
        return []

# ---------------------------------------------------------------------------
# UTILITY
# ---------------------------------------------------------------------------
def force_numeric(val) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


def filtra_privacy(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        c for c in df.columns
        if not any(x in str(c).upper() for x in COLONNE_NASCOSTE)
        and c != "GOOGLE_SHEET_ROW"
    ]
    return df[cols].dropna(how="all").copy()


def get_exact_col(columns, target: str):
    """Restituisce il nome colonna che corrisponde al target, o None."""
    matcher = COL_KEYWORDS.get(target)
    if not matcher:
        return None
    for col in columns:
        if matcher(str(col).upper().strip()):
            return col
    return None


def _retry(fn, *args, max_retries: int = 3, **kwargs) -> bool:
    """Esegue fn con backoff esponenziale in caso di eccezione."""
    for attempt in range(max_retries):
        try:
            fn(*args, **kwargs)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("Tentativo %d/%d fallito (%s), retry tra %ds", attempt + 1, max_retries, e, wait)
                time.sleep(wait)
            else:
                logger.error("Operazione fallita dopo %d tentativi: %s", max_retries, e)
    return False


# ---------------------------------------------------------------------------
# GENERAZIONE PDF
# ---------------------------------------------------------------------------
def generate_pdf(df_atleta: pd.DataFrame, nome_atleta: str) -> bytes | None:
    try:
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        cols  = df_atleta.columns.tolist()
        c_data = get_exact_col(cols, "DATA")
        c_km   = get_exact_col(cols, "KM")
        c_kmh  = get_exact_col(cols, "KMH")
        c_cal  = get_exact_col(cols, "CALORIE")
        c_prog = get_exact_col(cols, "PROGRAMMA")
        c_liv  = get_exact_col(cols, "LIVELLO")

        km_vals = df_atleta[c_km].apply(force_numeric)  if c_km  else pd.Series([0.0])
        kmh_avg = df_atleta[c_kmh].apply(force_numeric).mean() if c_kmh else 0.0
        cal_avg = df_atleta[c_cal].apply(force_numeric).mean() if c_cal else 0.0

        # ── Header ──────────────────────────────────────────────────────────
        pdf.set_fill_color(0, 80, 158)
        pdf.rect(0, 0, 210, 40, "F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("helvetica", "B", 20)
        pdf.set_y(12)
        pdf.cell(0, 10, "AQUATIME PERFORMANCE",             align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 12)
        pdf.cell(0, 10, f"REPORT: {nome_atleta.upper()}", align="C", new_x="LMARGIN", new_y="NEXT")

        # ── KPI ─────────────────────────────────────────────────────────────
        pdf.set_y(45)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "B", 11)
        pdf.set_fill_color(235, 235, 235)
        pdf.cell(63, 10, f"KM TOTALI: {km_vals.sum():.2f}", 1, 0, "C", True)
        pdf.cell(63, 10, f"KM/H MEDI: {kmh_avg:.1f}",       1, 0, "C", True)
        pdf.cell(64, 10, f"KCAL MEDIE: {cal_avg:.0f}",      1, 1, "C", True)
        pdf.ln(5)

        # ── Intestazione tabella ─────────────────────────────────────────────
        col_widths = [25, 45, 40, 20, 20, 25]
        headers    = ["Data", "Programma", "Livello", "Km", "Km/h", "Calorie"]
        pdf.set_font("helvetica", "B", 9)
        pdf.set_fill_color(0, 80, 158)
        pdf.set_text_color(255, 255, 255)
        for w, h in zip(col_widths, headers):
            pdf.cell(w, 8, h, 1, 0, "C", True)
        pdf.ln()

        # ── Righe dati ───────────────────────────────────────────────────────
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "", 8)
        for _, row in df_atleta.iterrows():
            data_val  = str(row.get(c_data, ""))
            solo_data = data_val.split(" ")[0] if " " in data_val else data_val
            pdf.cell(col_widths[0], 7, solo_data,                                    1, 0, "C")
            pdf.cell(col_widths[1], 7, str(row.get(c_prog, ""))[:MAX_PDF_PROG_LEN], 1, 0, "L")
            pdf.cell(col_widths[2], 7, str(row.get(c_liv,  ""))[:MAX_PDF_LIV_LEN],  1, 0, "L")
            pdf.cell(col_widths[3], 7, str(row.get(c_km,   "0")),                   1, 0, "C")
            pdf.cell(col_widths[4], 7, str(row.get(c_kmh,  "0")),                   1, 0, "C")
            pdf.cell(col_widths[5], 7, str(row.get(c_cal,  "0")),                   1, 1, "C")

        out = pdf.output()
        return bytes(out) if isinstance(out, bytearray) else out

    except Exception as e:
        logger.error("Errore PDF: %s", e)
        st.error(f"Errore generazione PDF: {e}")
        return None


# ===========================================================================
# APP PRINCIPALE
# ===========================================================================
check_auth()

try:
    dati_raw = fetch_all_data(ID_FOGLIO)

    # ── 1. LOGO ────────────────────────────────────────────────────────────
    _, c_c, _ = st.columns([1, 2, 1])
    with c_c:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.title("AQUATIME")

    # ── 2. RICERCA E REPORT PDF ────────────────────────────────────────────
    st.divider()
    with st.expander("🔍 **RICERCA ATLETA E REPORT PDF**", expanded=True):
        col1, col2 = st.columns(2)
        n_input = col1.text_input("Filtra Nome",    key="src_n")
        c_input = col2.text_input("Filtra Cognome", key="src_c")

        if (n_input or c_input) and dati_raw:
            df_full = pd.DataFrame(dati_raw)
            # regex=False: protegge da input tipo ".*" o "[a-z]+"
            mask = (
                df_full["Nome"].astype(str).str.contains(n_input, case=False, na=False, regex=False)
                & df_full["Cognome"].astype(str).str.contains(c_input, case=False, na=False, regex=False)
            )
            res = df_full[mask].copy()

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

                nome_file_pdf = f"Report_{datetime.now():%Y%m%d}_{n_input}_{c_input}.pdf".replace(" ", "_")
                pdf_out = generate_pdf(df_view, f"{n_input} {c_input}")
                if pdf_out:
                    st.download_button(
                        "📥 Scarica Report PDF", pdf_out,
                        nome_file_pdf, "application/pdf",
                        use_container_width=True
                    )
            else:
                st.warning("Nessun atleta trovato.")

    # ── 3. NUOVA SESSIONE ──────────────────────────────────────────────────
    #
    # Usiamo il workaround form_id invece di st.form perché i campi "Altro..."
    # richiedono widget condizionali che NON possono apparire dentro st.form
    # (Streamlit non permette rerun parziale all'interno di un form).
    # È la soluzione più stabile per questo caso d'uso specifico.
    # ───────────────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📝 Nuova Sessione")

    if "form_id" not in st.session_state:
        st.session_state.form_id = 0
    fid = st.session_state.form_id

    with st.container(border=True):
        f1, f2, f3 = st.columns(3)
        nome_ins    = f1.text_input("Nome *",    key=f"n_{fid}")
        cognome_ins = f2.text_input("Cognome *", key=f"c_{fid}")
        sede_ins    = f3.selectbox(
            "Sede *", ["Prati", "Corso Trieste"],
            index=None, placeholder="Scegli sede...", key=f"s_{fid}"
        )

        st.write("---")
        c1, c2, c3, c4 = st.columns(4)
        data_s  = c1.date_input("Data *", value=None, format="DD/MM/YYYY", key=f"d_{fid}")

        dur_sel = c2.selectbox(
            "Sessione *", ["30 min", "45 min", "Altro..."],
            index=None, key=f"dur_{fid}"
        )
        f_durata = c2.text_input("Specifica Sessione", key=f"dura_{fid}") if dur_sel == "Altro..." else dur_sel

        prg_sel = c3.selectbox(
            "Programma *", ["Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."],
            index=None, key=f"prg_{fid}"
        )
        f_prog = c3.text_input("Specifica Programma", key=f"prga_{fid}") if prg_sel == "Altro..." else prg_sel

        liv_sel = c4.selectbox(
            "Livello *",
            ["1-resistenza","2-resistenza","3-resistenza",
             "1-variabile","2-variabile","3-variabile",
             "4-variabile","5-variabile","6-variabile","Altro..."],
            index=None, key=f"liv_{fid}"
        )
        f_liv = c4.text_input("Specifica Livello", key=f"liva_{fid}") if liv_sel == "Altro..." else liv_sel

        st.write("---")
        f8, f9, f10 = st.columns(3)
        vel  = f8.number_input("Km/h *",    min_value=0.0, step=0.1, key=f"v_{fid}")
        dist = f9.number_input("Km *",      min_value=0.0, step=0.1, key=f"dist_{fid}")
        cal  = f10.number_input("Calorie *", min_value=0,             key=f"cal_{fid}")

        _, col_btn, _ = st.columns([2, 1, 2])
        if col_btn.button("💾 Salva Sessione", use_container_width=True):

            # ── Validazione ────────────────────────────────────────────────
            errori = []
            if not nome_ins:    errori.append("Nome")
            if not cognome_ins: errori.append("Cognome")
            if not sede_ins:    errori.append("Sede")
            if not data_s:      errori.append("Data")
            # Controllo campi "Altro..." : errore sia se non è stata fatta
            # nessuna selezione, sia se è stato scelto "Altro..." ma il campo
            # testo libero è rimasto vuoto
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
                        client = get_gspread_client()
                        sheet  = client.open_by_key(ID_FOGLIO).sheet1
                        riga   = [
                            f"{nome_ins} {cognome_ins}", nome_ins, cognome_ins,
                            0, "", data_s.strftime("%d/%m/%Y"),
                            f_durata, f_prog, f_liv,
                            vel, dist, cal, sede_ins, 0, 0, 0
                        ]
                        ok = _retry(sheet.append_row, riga)
                        if ok:
                            st.cache_data.clear()
                            st.session_state.form_id += 1
                            st.success("✅ Sessione salvata correttamente!")
                            st.rerun()
                        else:
                            st.error("❌ Salvataggio fallito dopo 3 tentativi. Controlla la connessione e riprova.")
                    except Exception as e:
                        logger.error("Errore salvataggio: %s", e)
                        st.error(f"Errore durante il salvataggio: {e}")

    # ── 4. ARCHIVIO RECENTE E CANCELLAZIONE ───────────────────────────────
    st.divider()
    st.subheader("📊 Archivio Recente (30gg)")

    if dati_raw:
        df_glob    = pd.DataFrame(dati_raw)
        c_data_g   = get_exact_col(df_glob.columns, "DATA")

        if c_data_g:
            df_glob[c_data_g] = pd.to_datetime(df_glob[c_data_g], dayfirst=True, errors="coerce")
            limite      = datetime.now() - timedelta(days=30)
            df_recenti  = df_glob[df_glob[c_data_g] >= limite].copy().sort_values(c_data_g, ascending=False)

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
                    scelta = st.selectbox(
                        "Seleziona la sessione da eliminare:",
                        opzioni,
                        format_func=lambda x: x["label"],
                        index=None
                    )

                    # ── Doppia conferma prima di cancellare ─────────────────
                    if scelta:
                        st.warning(
                            f"⚠️ Stai per eliminare: **{scelta['label']}**. "
                            "Questa azione è irreversibile."
                        )
                        col_si, col_no = st.columns(2)
                        if col_si.button("✅ Sì, elimina", use_container_width=True):
                            with st.spinner("Eliminazione in corso..."):
                                client = get_gspread_client()
                                sheet  = client.open_by_key(ID_FOGLIO).sheet1
                                ok = _retry(sheet.delete_rows, scelta["row_number"])
                                if ok:
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("❌ Eliminazione fallita. Riprova tra qualche istante.")
                        if col_no.button("❌ Annulla", use_container_width=True):
                            st.rerun()

except Exception as e:
    logger.error("Errore generale: %s", e)
    st.error(f"Errore generale: {e}")
