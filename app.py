import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
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
        return [r for r in data if r.get('Nome') and str(r.get('Nome')).strip() != ""]
    except Exception as e:
        return []

def force_numeric(val):
    if val is None or val == "": return 0.0
    try:
        return float(str(val).replace(',', '.').strip())
    except:
        return 0.0

def filtra_privacy(df):
    cols_to_keep = [c for c in df.columns if not any(x in str(c).upper() for x in COLONNE_NASCOSTE)]
    return df[cols_to_keep].dropna(how='all').copy()

# --- GENERAZIONE PDF ---
def generate_pdf(df_atleta, nome_atleta):
    try:
        # P = Portrait, mm = millimetri, A4
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # Identificazione colonne
        cols = df_atleta.columns.tolist()
        c_data = next((c for c in cols if "DATA" in c.upper() and "NASCITA" not in c.upper()), None)
        c_km = next((c for c in cols if c.upper() == "KM" or "KM TOTALI" in c.upper() or "KM PERCORSI" in c.upper()), None)
        c_kmh = next((c for c in cols if "KM/H" in c.upper() or "VELOCIT" in c.upper()), None)
        c_cal = next((c for c in cols if "CALORIE" in c.upper() or "KCAL" in c.upper()), None)
        c_prog = next((c for c in cols if "PROGRAMMA" in c.upper()), None)
        c_liv = next((c for c in cols if "LIVELLO" in c.upper()), None)

        # Statistiche
        km_tot = df_atleta[c_km].apply(force_numeric).sum() if c_km else 0
        kmh_avg = df_atleta[c_kmh].apply(force_numeric).mean() if c_kmh else 0
        cal_avg = df_atleta[c_cal].apply(force_numeric).mean() if c_cal else 0

        # Header PDF
        pdf.set_fill_color(0, 80, 158)
        pdf.rect(0, 0, 210, 40, 'F')
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 20)
        pdf.set_y(12)
        pdf.cell(0, 10, "AQUATIME PERFORMANCE", 0, 1, 'C')
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, f"REPORT PERFORMANCE: {nome_atleta.upper()}", 0, 1, 'C')
        
        # Riepilogo
        pdf.set_y(45)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 11)
        pdf.set_fill_color(235, 235, 235)
        pdf.cell(63, 10, f"KM TOTALI: {km_tot:.2f}", 1, 0, 'C', True)
        pdf.cell(63, 10, f"KM/H MEDI: {kmh_avg:.1f}", 1, 0, 'C', True)
        pdf.cell(64, 10, f"KCAL MEDIE: {cal_avg:.0f}", 1, 1, 'C', True)
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
        for _, row in df_atleta.iterrows():
            pdf.cell(w[0], 7, str(row.get(c_data, '')), 1, 0, 'C')
            pdf.cell(w[1], 7, str(row.get(c_prog, ''))[:22], 1, 0, 'L')
            pdf.cell(w[2], 7, str(row.get(c_liv, ''))[:20], 1, 0, 'L')
            # Valori distinti KM vs KM/H
            pdf.cell(w[3], 7, str(row.get(c_km, '0')), 1, 0, 'C')
            pdf.cell(w[4], 7, str(row.get(c_kmh, '0')), 1, 0, 'C')
            pdf.cell(w[5], 7, str(row.get(c_cal, '0')), 1, 1, 'C')

        return pdf.output(dest='S').encode('latin-1')
    except Exception as e:
        st.error(f"Errore generazione PDF: {e}")
        return None

# --- LOGICA APP ---
try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    dati_raw = fetch_all_data(ID_FOGLIO)

    # --- LOGO CENTRATO ---
    c_l, c_c, c_r = st.columns([1, 2, 1])
    with c_c:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.warning("File 'logo.png' non trovato nella cartella principale.")

    # --- RICERCA ---
    st.divider()
    with st.expander("🔍 **RICERCA ATLETA E REPORT**", expanded=True):
        col1, col2 = st.columns(2)
        n_input = col1.text_input("Filtra per Nome")
        c_input = col2.text_input("Filtra per Cognome")
        
        if (n_input or c_input) and dati_raw:
            df_full = pd.DataFrame(dati_raw)
            df_full.columns = [str(c).strip() for c in df_full.columns]
            
            # Filtro flessibile
            mask = (df_full['Nome'].str.contains(n_input, case=False, na=False)) & \
                   (df_full['Cognome'].str.contains(c_input, case=False, na=False))
            
            res = df_full[mask].copy()
            
            if not res.empty:
                # Ordinamento per data
                c_data = next((c for c in res.columns if "DATA" in c.upper() and "NASCITA" not in c.upper()), None)
                if c_data:
                    res[c_data] = pd.to_datetime(res[c_data], dayfirst=True, errors='coerce')
                    res = res.sort_values(c_data, ascending=False)
                
                df_view = filtra_privacy(res)
                
                # Creazione file PDF prima della formattazione estetica delle date
                pdf_bytes = generate_pdf(df_view, f"{n_input} {c_input}")
                
                # Formattazione per tabella a schermo
                if c_data:
                    df_view[c_data] = df_view[c_data].dt.strftime('%d/%m/%Y')
                
                st.dataframe(df_view, use_container_width=True)
                
                # --- PULSANTE DI SCARICO (Ora fuori dai sotto-cicli per essere sempre visibile) ---
                if pdf_bytes:
                    st.download_button(
                        label="📥 SCARICA REPORT PDF",
                        data=pdf_bytes,
                        file_name=f"Report_Aquatime_{n_input}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
            else:
                st.info("Nessun atleta trovato con questi criteri.")

    # --- FORM INSERIMENTO ---
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Registra Nuova Sessione")
        with st.form("main_form", clear_on_submit=True):
            f1, f2, f3 = st.columns(3)
            nome = f1.text_input("Nome *")
            cognome = f2.text_input("Cognome *")
            sede = f3.selectbox("Sede *", ["Prati", "Corso Trieste"], index=None)
            
            f4, f5, f6, f7 = st.columns(4)
            data_s = f4.date_input("Data *", format="DD/MM/YYYY")
            durata = f5.selectbox("Sessione *", ["30 min", "45 min", "Altro..."])
            prog = f6.selectbox("Programma *", ["Forma", "Expert", "Sportivo", "Salute", "Manuale"])
            liv = f7.selectbox("Livello *", ["1-res", "2-res", "3-res", "1-var", "2-var", "3-var"])
            
            f8, f9, f10 = st.columns(3)
            vel = f8.number_input("Velocità Media (Km/h) *", min_value=0.0, step=0.1)
            dist = f9.number_input("Distanza Totale (Km) *", min_value=0.0, step=0.1)
            cal = f10.number_input("Calorie *", min_value=0)

            if st.form_submit_button("Salva Dati"):
                if nome and cognome and sede:
                    client = get_gspread_client()
                    sheet = client.open_by_key(ID_FOGLIO).sheet1
                    riga = [f"{nome} {cognome}", nome, cognome, 0, "", data_s.strftime("%d/%m/%Y"), durata, prog, liv, vel, dist, cal, sede, 0, 0, 0]
                    sheet.append_row(riga)
                    st.cache_data.clear()
                    st.success("Sessione salvata con successo!")
                    st.rerun()
                else:
                    st.error("I campi con * sono obbligatori.")

except Exception as e:
    st.error(f"Errore di sistema: {e}")
