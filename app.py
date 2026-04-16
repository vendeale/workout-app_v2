import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from fpdf import FPDF
import io

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
        # FILTRO ANTI-NONE: Rimuove le righe dove il campo 'Nome' è vuoto o None
        return [r for r in data if r.get('Nome') and str(r.get('Nome')).strip() != ""]
    except Exception as e:
        st.error(f"Errore di connessione a Google Sheets: {e}")
        return []

# --- HELPER: IDENTIFICAZIONE COLONNE ---
def get_col_name(columns, keywords, avoid=None):
    for col in columns:
        c_up = str(col).upper().strip()
        if any(key.upper() in c_up for key in keywords):
            if avoid and any(a.upper() in c_up for a in avoid):
                continue
            return col
    return None

def filtra_privacy(df):
    cols_to_keep = [c for c in df.columns if not any(x in str(c).upper() for x in COLONNE_NASCOSTE)]
    return df[cols_to_keep].copy()

# --- FUNZIONE GENERAZIONE PDF (TABELLARE + RIEPILOGO) ---
def generate_pdf(df_atleta, nome, cognome):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    c_data = get_col_name(df_atleta.columns, ["DATA"], avoid=["NASCITA"])
    c_km = get_col_name(df_atleta.columns, ["KM TOTALI", "KM PERCORSI"])
    c_kmh = get_col_name(df_atleta.columns, ["KM/H", "VELOCITA"])
    c_cal = get_col_name(df_atleta.columns, ["CALORIE", "KCAL"])
    c_prog = get_col_name(df_atleta.columns, ["PROGRAMMA"])
    c_liv = get_col_name(df_atleta.columns, ["LIVELLO"])

    # Conversione numerica sicura per le medie
    km_vals = pd.to_numeric(df_atleta[c_km], errors='coerce').fillna(0)
    kmh_vals = pd.to_numeric(df_atleta[c_kmh], errors='coerce').fillna(0)
    cal_vals = pd.to_numeric(df_atleta[c_cal], errors='coerce').fillna(0)

    km_tot = km_vals.sum()
    kmh_avg = kmh_vals.mean() if not kmh_vals.empty else 0
    cal_avg = cal_vals.mean() if not cal_vals.empty else 0

    # Header Blu
    pdf.set_fill_color(0, 80, 158)
    pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_font("Arial", 'B', 22)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(10)
    pdf.cell(0, 10, "AQUATIME PERFORMANCE", 0, 1, 'C')
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Report Atleta: {nome.upper()} {cognome.upper()} | {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'C')
    
    pdf.set_y(45)
    pdf.set_text_color(0, 0, 0)
    
    # Riepilogo
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(245, 245, 245)
    pdf.cell(0, 10, "STATISTICHE GENERALI DEL PERIODO", 0, 1, 'L')
    pdf.set_font("Arial", '', 10)
    pdf.cell(63, 10, f"Km Totali: {km_tot:.1f}", 1, 0, 'C', True)
    pdf.cell(63, 10, f"Media Km/h: {kmh_avg:.1f}", 1, 0, 'C', True)
    pdf.cell(64, 10, f"Media Calorie: {cal_avg:.0f}", 1, 1, 'C', True)
    pdf.ln(5)

    # Tabella
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(0, 80, 158)
    pdf.set_text_color(255, 255, 255)
    w = [25, 45, 40, 20, 20, 25]
    headers = ["Data", "Programma", "Livello", "Km", "Km/h", "Calorie"]
    for i in range(len(headers)):
        pdf.cell(w[i], 8, headers[i], 1, 0, 'C', True)
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", '', 8)
    fill = False
    for _, row in df_atleta.iterrows():
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.cell(w[0], 7, str(row.get(c_data, '')), 1, 0, 'C', fill)
        pdf.cell(w[1], 7, str(row.get(c_prog, ''))[:22], 1, 0, 'L', fill)
        pdf.cell(w[2], 7, str(row.get(c_liv, ''))[:20], 1, 0, 'L', fill)
        pdf.cell(w[3], 7, str(row.get(c_km, '0')), 1, 0, 'C', fill)
        pdf.cell(w[4], 7, str(row.get(c_kmh, '0')), 1, 0, 'C', fill)
        pdf.cell(w[5], 7, str(row.get(c_cal, '0')), 1, 1, 'C', fill)
        fill = not fill

    return bytes(pdf.output())

# --- LOGICA APP ---
try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    dati_raw = fetch_all_data(ID_FOGLIO)

    st.markdown("<h2 style='text-align: center; color: #00509e;'>AQUATIME PERFORMANCE</h2>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- 1. RICERCA E REPORT ---
    st.divider()
    with st.expander("🔍 **RICERCA ATLETA E REPORT PDF**", expanded=False):
        c_search1, c_search2 = st.columns(2)
        with c_search1: s_nome = st.text_input("Nome:", key="sn")
        with c_search2: s_cognome = st.text_input("Cognome:", key="sc")
        
        if (s_nome or s_cognome) and dati_raw:
            df_tot = pd.DataFrame(dati_raw)
            df_tot.columns = [str(c).strip() for c in df_tot.columns]
            
            # Filtro ricerca
            mask = (df_tot['Nome'].astype(str).str.contains(s_nome.strip(), case=False, na=False)) & \
                   (df_tot['Cognome'].astype(str).str.contains(s_cognome.strip(), case=False, na=False))
            
            risultati = df_tot[mask].dropna(subset=['Nome']).copy()
            
            if not risultati.empty:
                col_data = get_col_name(risultati.columns, ["DATA"], avoid=["NASCITA"])
                if col_data:
                    risultati[col_data] = pd.to_datetime(risultati[col_data], dayfirst=True, errors='coerce')
                    risultati = risultati.sort_values(col_data)
                
                df_display = filtra_privacy(risultati)
                if col_data and col_data in df_display.columns:
                    df_display[col_data] = df_display[col_data].dt.strftime('%d/%m/%Y')
                
                st.dataframe(df_display.iloc[::-1], use_container_width=True)
                pdf_file = generate_pdf(df_display, s_nome, s_cognome)
                st.download_button("📥 Scarica Report PDF", pdf_file, f"Report_{s_nome}_{s_cognome}.pdf", "application/pdf")
            else:
                st.warning("Nessun risultato trovato.")

    # --- 2. FORM INSERIMENTO ---
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Nuova Sessione")
        with st.form("workout_form", clear_on_submit=True):
            r1c1, r1c2, r1c3 = st.columns(3)
            with r1c1: n_ins = st.text_input("Nome *")
            with r1c2: c_ins = st.text_input("Cognome *")
            with r1c3: s_ins = st.selectbox("Sede *", ["", "Prati", "Corso Trieste"])
            
            st.divider()
            r2c1, r2c2, r2c3, r2c4 = st.columns(4)
            with r2c1: d_ins = st.date_input("Data *", format="DD/MM/YYYY")
            with r2c2: sess_sel = st.selectbox("Sessione *", ["30 min", "45 min", "Altro..."])
            with r2c3: prog_sel = st.selectbox("Programma *", ["Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."])
            with r2c4: liv_sel = st.selectbox("Livello *", ["1-res", "2-res", "3-res", "1-var", "2-var", "3-var", "Altro..."])

            st.divider()
            r3c1, r3c2, r3c3 = st.columns(3)
            with r3c1: v_ins = st.number_input("Km/h *", min_value=0.0, step=0.1)
            with r3c2: k_ins = st.number_input("Km totali *", min_value=0.0, step=0.1)
            with r3c3: cl_ins = st.number_input("Calorie *", min_value=0)

            if st.form_submit_button("🚀 Salva"):
                if not n_ins or not c_ins or not s_ins:
                    st.error("Campi obbligatori mancanti!")
                else:
                    client = get_gspread_client()
                    sheet = client.open_by_key(ID_FOGLIO).sheet1
                    riga = [f"{n_ins} {c_ins}", n_ins, c_ins, 0, "", d_ins.strftime("%d/%m/%Y"), sess_sel, prog_sel, liv_sel, v_ins, k_ins, cl_ins, s_ins, 0, 0, 0]
                    sheet.append_row(riga)
                    st.cache_data.clear()
                    st.success("Salvato!")
                    st.rerun()

    # --- 3. STORICO E CANCELLAZIONE ---
    st.divider()
    st.subheader("📊 Gestione Archivio")
    
    if dati_raw:
        df_glob = pd.DataFrame(dati_raw)
        df_glob.columns = [str(c).strip() for c in df_glob.columns]
        
        st.write("Ultime sessioni (Colonne sensibili nascoste):")
        df_glob_privacy = filtra_privacy(df_glob)
        # Rimuove righe None dalla visualizzazione globale
        df_glob_privacy = df_glob_privacy.dropna(subset=['Nome'])
        st.dataframe(df_glob_privacy.tail(15).iloc[::-1], use_container_width=True)

        with st.expander("🗑️ **CANCELLA INSERIMENTO ERRATO**"):
            st.warning("Attenzione: l'eliminazione è irreversibile.")
            opzioni_delete = []
            col_d_p = get_col_name(df_glob.columns, ["DATA"], avoid=["NASCITA"]) or "Data Pedalata"
            for i, r in enumerate(dati_raw):
                # Usiamo dati_raw originale per avere l'indice corretto di riga
                label = f"Riga {i+2}: {r.get('Nome','')} {r.get('Cognome','')} - {r.get(col_d_p,'')}"
                opzioni_delete.append({"label": label, "index": i + 2})
            
            scelta = st.selectbox("Seleziona la riga da rimuovere:", options=opzioni_delete[::-1], format_func=lambda x: x["label"])
            if st.button("Conferma Eliminazione"):
                client = get_gspread_client()
                sheet = client.open_by_key(ID_FOGLIO).sheet1
                sheet.delete_rows(scelta["index"])
                st.cache_data.clear()
                st.success(f"Riga {scelta['index']} eliminata!")
                st.rerun()

except Exception as e:
    st.error(f"Errore generale: {e}")
