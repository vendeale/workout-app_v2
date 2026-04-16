import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from fpdf import FPDF
import io
import os

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Aquatime Workout Manager", page_icon="🚴‍♂️", layout="wide")

# --- COSTANTI PRIVACY ---
COLONNE_NASCOSTE = ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"]

# --- FUNZIONI DI ACCESSO AI DATI ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def fetch_all_data(id_foglio):
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(id_foglio)
        sheet = spreadsheet.sheet1
        data = sheet.get_all_records()
        cleaned_data = []
        for i, r in enumerate(data):
            new_r = {str(k).strip(): v for k, v in r.items()}
            new_r['GOOGLE_SHEET_ROW'] = i + 2
            if new_r.get('Nome') and str(new_r.get('Nome')).strip() != "":
                cleaned_data.append(new_r)
        return cleaned_data
    except:
        return []

def force_numeric(val):
    if val is None or val == "": return 0.0
    try:
        return float(str(val).replace(',', '.').strip())
    except:
        return 0.0

def filtra_privacy(df):
    cols_to_keep = [c for c in df.columns if not any(x in str(c).upper() for x in COLONNE_NASCOSTE) and c != 'GOOGLE_SHEET_ROW']
    return df[cols_to_keep].dropna(how='all').copy()

def get_exact_col(columns, target):
    cols_up = [str(c).upper().strip() for c in columns]
    if target == "KMH":
        for i, c in enumerate(cols_up):
            if "KM/H" in c or "VELOCIT" in c: return columns[i]
    if target == "KM":
        for i, c in enumerate(cols_up):
            if "KM" in c and "KM/H" not in c and "VELOCIT" not in c: return columns[i]
            if "DISTANZA" in c: return columns[i]
    if target == "DATA":
        for i, c in enumerate(cols_up):
            if "DATA" in c and "NASCITA" not in c: return columns[i]
    if target == "CALORIE":
        for i, c in enumerate(cols_up):
            if "CAL" in c or "KCAL" in c: return columns[i]
    if target == "PROGRAMMA":
        for i, c in enumerate(cols_up):
            if "PROGR" in c: return columns[i]
    if target == "LIVELLO":
        for i, c in enumerate(cols_up):
            if "LIV" in c: return columns[i]
    return None

def generate_pdf(df_atleta, nome_atleta):
    try:
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        cols = df_atleta.columns.tolist()
        c_data = get_exact_col(cols, "DATA")
        c_km = get_exact_col(cols, "KM")
        c_kmh = get_exact_col(cols, "KMH")
        c_cal = get_exact_col(cols, "CALORIE")
        c_prog = get_exact_col(cols, "PROGRAMMA")
        c_liv = get_exact_col(cols, "LIVELLO")
        km_vals = df_atleta[c_km].apply(force_numeric) if c_km else pd.Series([0.0])
        kmh_avg = df_atleta[c_kmh].apply(force_numeric).mean() if c_kmh else 0.0
        cal_avg = df_atleta[c_cal].apply(force_numeric).mean() if c_cal else 0.0
        pdf.set_fill_color(0, 80, 158)
        pdf.rect(0, 0, 210, 40, 'F')
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("helvetica", 'B', 20)
        pdf.set_y(12)
        pdf.cell(0, 10, "AQUATIME PERFORMANCE", align='C', new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", '', 12)
        pdf.cell(0, 10, f"REPORT PERFORMANCE: {nome_atleta.upper()}", align='C', new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(45)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", 'B', 11)
        pdf.set_fill_color(235, 235, 235)
        pdf.cell(63, 10, f"KM TOTALI: {km_vals.sum():.2f}", 1, 0, 'C', True)
        pdf.cell(63, 10, f"KM/H MEDI: {kmh_avg:.1f}", 1, 0, 'C', True)
        pdf.cell(64, 10, f"KCAL MEDIE: {cal_avg:.0f}", 1, 1, 'C', True)
        pdf.ln(5)
        pdf.set_font("helvetica", 'B', 9)
        pdf.set_fill_color(0, 80, 158)
        pdf.set_text_color(255, 255, 255)
        w = [25, 45, 40, 20, 20, 25]
        headers = ["Data", "Programma", "Livello", "Km", "Km/h", "Calorie"]
        for i in range(len(headers)):
            pdf.cell(w[i], 8, headers[i], 1, 0, 'C', True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", '', 8)
        for _, row in df_atleta.iterrows():
            data_val = str(row.get(c_data, ''))
            solo_data = data_val.split(' ')[0] if ' ' in data_val else data_val
            pdf.cell(w[0], 7, solo_data, 1, 0, 'C')
            pdf.cell(w[1], 7, str(row.get(c_prog, ''))[:22], 1, 0, 'L')
            pdf.cell(w[2], 7, str(row.get(c_liv, ''))[:20], 1, 0, 'L')
            pdf.cell(w[3], 7, str(row.get(c_km, '0')), 1, 0, 'C')
            pdf.cell(w[4], 7, str(row.get(c_kmh, '0')), 1, 0, 'C')
            pdf.cell(w[5], 7, str(row.get(c_cal, '0')), 1, 1, 'C')
        pdf_output = pdf.output()
        return bytes(pdf_output) if isinstance(pdf_output, bytearray) else pdf_output
    except Exception as e:
        st.error(f"Errore generazione PDF: {e}")
        return None

# --- LOGICA APP ---
try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    dati_raw = fetch_all_data(ID_FOGLIO)

    # 1. LOGO
    c_l, c_c, c_r = st.columns([1, 2, 1])
    with c_c:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        else: st.title("AQUATIME")

    # 2. RICERCA E REPORT
    st.divider()
    with st.expander("🔍 **RICERCA ATLETA E REPORT PDF**", expanded=True):
        col1, col2 = st.columns(2)
        n_input = col1.text_input("Filtra Nome", key="src_n")
        c_input = col2.text_input("Filtra Cognome", key="src_c")
        if (n_input or c_input) and dati_raw:
            df_full = pd.DataFrame(dati_raw)
            res = df_full[(df_full['Nome'].astype(str).str.contains(n_input, case=False, na=False)) & 
                          (df_full['Cognome'].astype(str).str.contains(c_input, case=False, na=False))].copy()
            if not res.empty:
                c_data = get_exact_col(res.columns, "DATA")
                if c_data:
                    res[c_data] = pd.to_datetime(res[c_data], dayfirst=True, errors='coerce')
                    res = res.sort_values(c_data, ascending=False)
                df_view = filtra_privacy(res)
                df_display = df_view.copy()
                if c_data:
                    df_display[c_data] = df_display[c_data].dt.strftime('%d/%m/%Y')
                st.dataframe(df_display, use_container_width=True)
                data_oggi = datetime.now().strftime("%Y%m%d")
                nome_atleta_pulito = f"{n_input}_{c_input}".replace(" ", "_")
                nome_file_pdf = f"Report_{data_oggi}_{nome_atleta_pulito}.pdf"
                pdf_out = generate_pdf(df_view, f"{n_input} {c_input}")
                if pdf_out:
                    st.download_button("📥 Scarica Report PDF", pdf_out, nome_file_pdf, "application/pdf", use_container_width=True)
            else:
                st.warning("Nessun atleta trovato.")

    # 3. NUOVA SESSIONE (VERSIONE RESET STABILE CON KEY DINAMICA)
    st.divider()
    st.subheader("📝 Nuova Sessione")

    # Trucco infallibile per il reset: cambiamo il prefisso del form ad ogni salvataggio
    if 'form_id' not in st.session_state:
        st.session_state.form_id = 0

    # Usiamo il form_id per generare chiavi nuove dopo ogni salvataggio
    fid = st.session_state.form_id

    with st.container(border=True):
        f1, f2, f3 = st.columns(3)
        nome_ins = f1.text_input("Nome *", key=f"n_{fid}")
        cognome_ins = f2.text_input("Cognome *", key=f"c_{fid}")
        sede_ins = f3.selectbox("Sede *", ["Prati", "Corso Trieste"], index=None, placeholder="Scegli sede...", key=f"s_{fid}")
        
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
            
        liv_sel = c4.selectbox("Livello *", ["1-resistenza", "2-resistenza", "3-resistenza", "1-variabile", "2-variabile", "3-variabile", "4-variabile", "5-variabile", "6-variabile", "Altro..."], index=None, key=f"liv_{fid}")
        f_liv = liv_sel
        if liv_sel == "Altro...": 
            f_liv = c4.text_input("Specifica Livello", key=f"liva_{fid}")

        st.write("---")
        f8, f9, f10 = st.columns(3)
        vel = f8.number_input("Km/h *", min_value=0.0, step=0.1, key=f"v_{fid}")
        dist = f9.number_input("Km *", min_value=0.0, step=0.1, key=f"dist_{fid}")
        cal = f10.number_input("Calorie *", min_value=0, key=f"cal_{fid}")

        _, col_btn, _ = st.columns([2, 1, 2])
        if col_btn.button("Salva Sessione", use_container_width=True):
            if nome_ins and cognome_ins and sede_ins and data_s and f_durata and f_prog and f_liv:
                try:
                    client = get_gspread_client()
                    sheet = client.open_by_key(ID_FOGLIO).sheet1
                    riga = [f"{nome_ins} {cognome_ins}", nome_ins, cognome_ins, 0, "", data_s.strftime("%d/%m/%Y"), f_durata, f_prog, f_liv, vel, dist, cal, sede_ins, 0, 0, 0]
                    sheet.append_row(riga)
                    
                    st.cache_data.clear()
                    # Incrementando il form_id, tutte le chiavi dei widget cambiano.
                    # Per Streamlit sono widget nuovi, quindi appaiono vuoti.
                    st.session_state.form_id += 1
                    
                    st.success("Salvato correttamente!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante il salvataggio: {e}")
            else: 
                st.error("Compila i campi obbligatori (*)")

    # 4. ARCHIVIO E CANCELLAZIONE
    st.divider()
    st.subheader("📊 Archivio Recente (30gg)")
    if dati_raw:
        df_glob = pd.DataFrame(dati_raw)
        c_data_g = get_exact_col(df_glob.columns, "DATA")
        if c_data_g:
            df_glob[c_data_g] = pd.to_datetime(df_glob[c_data_g], dayfirst=True, errors='coerce')
            limite = datetime.now() - timedelta(days=30)
            df_recenti = df_glob[df_glob[c_data_g] >= limite].copy().sort_values(c_data_g, ascending=False)
            if not df_recenti.empty:
                df_rec_disp = filtra_privacy(df_recenti)
                df_rec_disp[c_data_g] = df_rec_disp[c_data_g].dt.strftime('%d/%m/%Y')
                st.dataframe(df_rec_disp, use_container_width=True)
                with st.expander("🗑️ Cancella una riga dall'archivio"):
                    opzioni_cancella = []
                    for _, r in df_recenti.iterrows():
                        label = f"{r[c_data_g].strftime('%d/%m/%Y')} - {r['Nome']} {r['Cognome']}"
                        opzioni_cancella.append({"label": label, "row_number": r['GOOGLE_SHEET_ROW']})
                    scelta = st.selectbox("Seleziona la sessione da eliminare:", opzioni_cancella, format_func=lambda x: x["label"], index=None)
                    if st.button("Elimina Sessione"):
                        if scelta:
                            client = get_gspread_client()
                            sheet = client.open_by_key(ID_FOGLIO).sheet1
                            sheet.delete_rows(scelta['row_number'])
                            st.cache_data.clear()
                            st.rerun()

except Exception as e:
    st.error(f"Errore generale: {e}")
