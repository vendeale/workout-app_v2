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
ID_FOGLIO           = st.secrets["ID_FOGLIO"]
COLONNE_NASCOSTE    = ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"]
GOOGLE_SHEET_OFFSET = 2      # riga 1 = intestazione → dati dalla riga 2
CACHE_TTL           = 600    # secondi (10 minuti)
CLIENT_TTL          = 3000   # secondi (50 minuti) — token Google scadono a 60 min
MAX_PDF_PROG_LEN    = 22
MAX_PDF_LIV_LEN     = 20
MAX_INPUT_LEN       = 100    # caratteri massimi per i campi testo libero

# Mapping colonne: chiave → funzione che riceve il nome colonna in UPPERCASE
COL_KEYWORDS: dict = {
    "KMH":       lambda c: "KM/H" in c or "VELOCIT" in c,
    "KM":        lambda c: ("KM" in c and "KM/H" not in c and "VELOCIT" not in c) or "DISTANZA" in c,
    "DATA":      lambda c: "DATA" in c and "NASCITA" not in c,
    "CALORIE":   lambda c: "CAL" in c or "KCAL" in c,
    "PROGRAMMA": lambda c: "PROGR" in c,
    "LIVELLO":   lambda c: "LIV" in c,
}

# ---------------------------------------------------------------------------
# AUTENTICAZIONE OPZIONALE
# ---------------------------------------------------------------------------
def check_auth() -> None:
    """
    Attiva la password SOLO se 'app_password' è presente in st.secrets.
    Se non configurata, l'app rimane accessibile senza login.
    Per attivarla aggiungi nel secrets.toml:
        app_password = "la-tua-password"
    """
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
    """
    Previene formula injection in Google Sheet.
    Se il valore inizia con =, +, -, @, |, % aggiunge un apostrofo iniziale
    che forza Google Sheet a trattarlo come testo e non come formula.
    Tronca inoltre a MAX_INPUT_LEN caratteri.
    """
    val = str(val).strip()[:MAX_INPUT_LEN]
    if val and val[0] in ("=", "+", "-", "@", "|", "%"):
        return "'" + val
    return val

# ---------------------------------------------------------------------------
# ACCESSO AI DATI
# ---------------------------------------------------------------------------
@st.cache_resource(ttl=CLIENT_TTL)
def get_gspread_client():
    """
    Crea il client gspread con TTL di 50 minuti per prevenire
    la scadenza del token Google (che avviene a 60 minuti).
    Scope ridotto a solo 'spreadsheets' — non serve accesso a Drive.
    """
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)


@st.cache_resource(ttl=CLIENT_TTL)
def get_sheet():
    """Oggetto sheet cachato — evita di riaprire il foglio ad ogni scrittura."""
    return get_gspread_client().open_by_key(ID_FOGLIO).sheet1


@st.cache_data(ttl=CACHE_TTL)
def fetch_all_data(id_foglio: str) -> list[dict]:
    """
    Legge tutti i record dal foglio Google.
    numericise_ignore=['all'] impedisce a gspread di convertire
    autonomamente i numeri: '17,1' resta stringa '17,1' e viene
    poi convertito correttamente da normalizza_numerici.
    Rilancia l'eccezione invece di chiamare st.error() dentro la
    funzione cached (le funzioni cached non devono avere side effect UI).
    """
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
# UTILITY
# ---------------------------------------------------------------------------
def force_numeric(val) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


def normalizza_numerici(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converte le colonne numeriche (km, km/h, calorie) da stringa con virgola
    decimale (es. '18,7') a float corretto (18.7).
    Usa operazioni vettorizzate pandas invece di .apply() riga per riga
    per prestazioni migliori su dataset grandi.
    """
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
    """
    Costruisce e normalizza il DataFrame una volta sola per rerun,
    salvandolo in session_state per evitare di rielaborare gli stessi
    dati in più punti dell'app (ricerca + archivio).
    Usa data_version come chiave univoca invece di len(dati_raw):
    questo evita il caso limite in cui cancellazione + inserimento
    riportino il conteggio righe al valore precedente, riusando
    erroneamente il DataFrame vecchio dalla session_state.
    """
    if "data_version" not in st.session_state:
        st.session_state.data_version = 0
    chiave = f"df_norm_{st.session_state.data_version}"
    if chiave not in st.session_state:
        st.session_state[chiave] = normalizza_numerici(pd.DataFrame(dati_raw))
    return st.session_state[chiave].copy()


def invalida_df_cache():
    """
    Incrementa data_version e rimuove il DataFrame precedente dalla
    session_state dopo ogni scrittura o cancellazione, forzando la
    ricostruzione al prossimo rerun con i dati aggiornati.
    """
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
                logger.warning(
                    "Tentativo %d/%d fallito (%s), retry tra %ds",
                    attempt + 1, max_retries, e, wait
                )
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

        # ── Header ──────────────────────────────────────────────────────────
        pdf.set_fill_color(0, 80, 158)
        pdf.rect(0, 0, 210, 40, "F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("helvetica", "B", 20)
        pdf.set_y(12)
        pdf.cell(0, 10, "AQUATIME PERFORMANCE", align="C", new_x="LMARGIN", new_y="NEXT")
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
        logger.error("Errore PDF: %s", e)
        st.error(f"Errore generazione PDF: {e}")
        return None


# ===========================================================================
# APP PRINCIPALE
# ===========================================================================
check_auth()

try:
    # fetch_all_data ora rilancia l'eccezione → la gestiamo qui fuori
    try:
        dati_raw = fetch_all_data(ID_FOGLIO)
    except Exception as e:
        logger.error("Errore fetch dati: %s", e)
        st.error(f"Impossibile caricare i dati dal foglio: {e}")
        st.stop()

    # DataFrame normalizzato costruito una volta sola per rerun
    df_norm = get_df_normalizzato(dati_raw)

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
        n_input = col1.text_input("Filtra Nome",    key="src_n", max_chars=MAX_INPUT_LEN)
        c_input = col2.text_input("Filtra Cognome", key="src_c", max_chars=MAX_INPUT_LEN)

        if (n_input or c_input) and dati_raw:
            # regex=False: protegge da input tipo ".*" o "[a-z]+"
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

            # ── Validazione ────────────────────────────────────────────────
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
                            st.error("❌ Salvataggio fallito dopo 3 tentativi. Controlla la connessione e riprova.")
                    except Exception as e:
                        logger.error("Errore salvataggio: %s", e)
                        st.error(f"Errore durante il salvataggio: {e}")

    # ── 4. ARCHIVIO RECENTE E CANCELLAZIONE ───────────────────────────────
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

                    # ── Doppia conferma prima di cancellare ─────────────────
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
                                    st.error("❌ Eliminazione fallita. Riprova tra qualche istante.")
                        if col_no.button("❌ Annulla", use_container_width=True):
                            del st.session_state["sel_cancella"]
                            st.rerun()

except Exception as e:
    logger.error("Errore generale: %s", e)
    st.error(f"Errore generale: {e}")
