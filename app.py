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

def get_col_name(columns, keywords, avoid=None):
    for col in columns:
        c_up = str(col).upper().strip()
        if any(key.upper() in c_up for key in keywords):
            if avoid and any(a.upper() in c_up for a in avoid):
                continue
            return col
    return None

# --- GENERAZIONE PDF ---
def generate_pdf(df_atleta, nome_atleta):
    try:
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        cols = df_atleta.columns.tolist()
        c_data = get_col_name(cols, ["DATA"], avoid=["NASCITA"])
        c_km = get_col_name(cols, ["KM TOTALI", "KM PERCORSI"]) or "KM"
        c_kmh = get_col_name(cols, ["KM/H", "VELOCIT"])
        c_cal = get_col_name(cols, ["CALORIE", "KCAL"])
        c_prog = get_col_name(cols, ["PROGRAMMA"])
        c_liv = get_col_name(cols, ["LIVELLO"])

        km_tot = df_atleta[c_km].apply(force_numeric).sum()
        kmh_avg = df_atleta[c_kmh].apply(force_numeric).mean()
        cal_avg = df_atleta[c_cal].apply(force_numeric).mean()

        # Header
        pdf.set_fill_color(0, 80, 158)
        pdf.rect(0, 0, 210, 40, 'F')
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 20)
        pdf.set_y(12)
        pdf.cell(0, 10, "AQUATIME PERFORMANCE", 0, 1, 'C')
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, f"REPORT PERFORMANCE: {nome_atleta.upper()}", 0, 1, 'C')
        
        # Riepilogo Statistico
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
            pdf.cell(w[3], 7, str(row.get(c_km, '0')), 1, 0, 'C')
            pdf.cell(w[4], 7, str(row.get(c_kmh, '0')), 1, 0, 'C')
            pdf.cell(w[5], 7, str(row.get(c_cal, '0')), 1, 1, 'C')

        return pdf.output(dest='S').encode('latin-1')
    except Exception as e:
        st.error(f"Errore PDF: {e}")
        return None

# --- LOGICA APP ---
try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    dati_raw = fetch_all_data(ID_FOGLIO)

    # 1. LOGO CENTRATO
    c_l, c_c, c_r = st.columns([1, 2, 1])
    with c_c:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.title("AQUATIME")

    # 2. RICERCA E REPORT
    st.divider()
    with st.expander("🔍 **RICERCA ATLETA E REPORT PDF**", expanded=False):
        col1, col2 = st.columns(2)
        n_input = col1.text_input("Filtra Nome")
        c_input = col2.text_input("Filtra Cognome")
        
        if (n_input or c_input) and dati_raw:
            df_full = pd.DataFrame(dati_raw)
            df_full.columns = [str(c).strip() for c in df_full.columns]
            res = df_full[(df_full['Nome'].str.contains(n_input, case=False, na=False)) & 
                          (df_full['Cognome'].str.contains(c_input, case=False, na=False))].copy()
            
            if not res.empty:
                c_data = get_col_name(res.columns, ["DATA"], avoid=["NASCITA"])
                if c_data:
                    res[c_data] = pd.to_datetime(res[c_data], dayfirst=True, errors='coerce')
                    res = res.sort_values(c_data, ascending=False)
                
                df_view = filtra_privacy(res)
                pdf_bytes = generate_pdf(df_view, f"{n_input} {c_input}")
                
                if c_data:
                    df_view[c_data] = df_view[c_data].dt.strftime('%d/%m/%Y')
                
                st.dataframe(df_view, use_container_width=True)
                if pdf_bytes:
                    st.download_button("📥 Scarica Report PDF", pdf_bytes, f"Report_{n_input}.pdf", "application/pdf", use_container_width=True)

    # 3. FORM INSERIMENTO
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Nuova Sessione")
        with st.form("insert_form", clear_on_submit=True):
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
            vel = f8.number_input("Km/h *", min_value=0.0, step=0.1)
            dist = f9.number_input("Km *", min_value=0.0, step=0.1)
            cal = f10.number_input("Calorie *", min_value=0)

            if st.form_submit_button("Salva sessione"):
                if nome and cognome and sede:
                    client = get_gspread_client()
                    sheet = client.open_by_key(ID_FOGLIO).sheet1
                    riga = [f"{nome} {cognome}", nome, cognome, 0, "", data_s.strftime("%d/%m/%Y"), durata, prog, liv, vel, dist, cal, sede, 0, 0, 0]
                    sheet.append_row(riga)
                    st.cache_data.clear()
                    st.success("Dati inviati!")
                    st.rerun()

    # 4. STORICO 30 GIORNI E CANCELLAZIONE
    st.divider()
    st.subheader("📊 Archivio Recente (Ultimi 30 giorni)")
    if dati_raw:
        df_glob = pd.DataFrame(dati_raw)
        df_glob.columns = [str(c).strip() for c in df_glob.columns]
        c_data_g = get_col_name(df_glob.columns, ["DATA"], avoid=["NASCITA"])
        
        if c_data_g:
            df_glob[c_data_g] = pd.to_datetime(df_glob[c_data_g], dayfirst=True, errors='coerce')
            limite = datetime.now() - timedelta(days=30)
            df_recenti = df_glob[df_glob[c_data_g] >= limite].copy()
            
            if not df_recenti.empty:
                df_rec_view = filtra_privacy(df_recenti).sort_values(c_data_g, ascending=False)
                df_rec_view[c_data_g] = df_rec_view[c_data_g].dt.strftime('%d/%m/%Y')
                st.dataframe(df_rec_view, use_container_width=True)

                with st.expander("🗑️ Cancella una riga dall'archivio"):
                    opzioni = []
                    # Creiamo una lista per la selectbox (mostriamo le ultime 30 righe del foglio)
                    for idx, r in df_recenti.iterrows():
                        d_str = r[c_data_g].strftime('%d/%m/%Y')
                        label = f"Riga {idx+2}: {r.get('Nome','')} {r.get('Cognome','')} - {d_str}"
                        opzioni.append({"label": label, "index": idx+2})
                    
                    scelta = st.selectbox("Seleziona riga da eliminare:", opzioni, format_func=lambda x: x["label"], index=None)
                    if st.button("Conferma Eliminazione", type="primary"):
                        if scelta:
                            client = get_gspread_client()
                            sheet = client.open_by_key(ID_FOGLIO).sheet1
                            sheet.delete_rows(scelta["index"])
                            st.cache_data.clear()
                            st.success("Riga eliminata!")
                            st.rerun()
            else:
                st.info("Nessuna sessione negli ultimi 30 giorni.")

except Exception as e:
    st.error(f"Errore: {e}")
