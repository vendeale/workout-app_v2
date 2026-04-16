import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
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
        return [r for r in data if r.get('Nome') and str(r.get('Nome')).strip() != ""]
    except Exception as e:
        return []

# --- HELPER ---
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
    return df[cols_to_keep].dropna(how='all').copy()

# --- GENERAZIONE PDF ---
def generate_pdf(df_atleta, nome, cognome):
    try:
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        c_data = get_col_name(df_atleta.columns, ["DATA"], avoid=["NASCITA"])
        c_km = get_col_name(df_atleta.columns, ["KM TOTALI", "KM PERCORSI", "KM"])
        c_kmh = get_col_name(df_atleta.columns, ["KM/H", "VELOCITA"])
        c_cal = get_col_name(df_atleta.columns, ["CALORIE", "KCAL"])
        c_prog = get_col_name(df_atleta.columns, ["PROGRAMMA"])
        c_liv = get_col_name(df_atleta.columns, ["LIVELLO"])

        def force_numeric(val):
            if val is None or val == "": return 0.0
            try:
                s = str(val).replace(',', '.').strip()
                return float(s)
            except:
                return 0.0

        km_vals = df_atleta[c_km].apply(force_numeric) if c_km else pd.Series([0.0])
        km_tot = km_vals.sum()
        kmh_avg = df_atleta[c_kmh].apply(force_numeric).mean() if c_kmh else 0.0
        cal_avg = df_atleta[c_cal].apply(force_numeric).mean() if c_cal else 0.0

        tz_roma = pytz.timezone('Europe/Rome')
        data_ora_roma = datetime.now(tz_roma).strftime("%d/%m/%Y %H:%M:%S")

        pdf.set_fill_color(0, 80, 158)
        pdf.rect(0, 0, 210, 45, 'F')
        pdf.set_font("Arial", 'B', 20)
        pdf.set_text_color(255, 255, 255)
        pdf.set_y(10)
        pdf.cell(0, 10, "AQUATIME PERFORMANCE", 0, 1, 'C')
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, f"REPORT ATLETA: {nome.upper()} {cognome.upper()}", 0, 1, 'C')
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 8, f"Generato a Roma il: {data_ora_roma}", 0, 1, 'C')
        
        pdf.set_y(50)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 12)
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(0, 10, "RIEPILOGO GENERALE", 0, 1, 'L')
        pdf.set_font("Arial", '', 10)
        pdf.cell(63, 10, f"Km Totali: {km_tot:.2f}", 1, 0, 'C', True)
        pdf.cell(63, 10, f"Media Km/h: {kmh_avg:.1f}", 1, 0, 'C', True)
        pdf.cell(64, 10, f"Media Calorie: {cal_avg:.0f}", 1, 1, 'C', True)
        pdf.ln(5)

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

        return bytes(pdf.output())
    except Exception as e:
        return None

# --- LOGICA APP ---
try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    dati_raw = fetch_all_data(ID_FOGLIO)

    st.markdown("<h2 style='text-align: center; color: #00509e;'>AQUATIME PERFORMANCE</h2>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- 1. RICERCA ---
    st.divider()
    with st.expander("🔍 **RICERCA ATLETA E REPORT PDF**", expanded=False):
        c1, c2 = st.columns(2)
        s_nome = c1.text_input("Nome:", key="sn").strip()
        s_cognome = c2.text_input("Cognome:", key="sc").strip()
        
        if (s_nome or s_cognome) and dati_raw:
            df_tot = pd.DataFrame(dati_raw)
            df_tot.columns = [str(c).strip() for c in df_tot.columns]
            mask = (df_tot['Nome'].astype(str).str.contains(s_nome, case=False, na=False)) & \
                   (df_tot['Cognome'].astype(str).str.contains(s_cognome, case=False, na=False))
            
            risultati = df_tot[mask].copy()
            if not risultati.empty:
                nome_reale = risultati.iloc[0]['Nome']
                cognome_reale = risultati.iloc[0]['Cognome']
                col_data = get_col_name(risultati.columns, ["DATA"], avoid=["NASCITA"])
                
                if col_data:
                    risultati[col_data] = pd.to_datetime(risultati[col_data], dayfirst=True, errors='coerce')
                    risultati = risultati.sort_values(col_data)
                
                df_display = filtra_privacy(risultati)
                if col_data and col_data in df_display.columns:
                    df_display[col_data] = df_display[col_data].dt.strftime('%d/%m/%Y')
                
                st.dataframe(df_display.iloc[::-1], use_container_width=True)
                pdf_file = generate_pdf(df_display, nome_reale, cognome_reale)
                if pdf_file:
                    n_file = f"Report_{nome_reale}_{cognome_reale}.pdf".replace(" ", "_")
                    st.download_button("📥 Scarica Report PDF", pdf_file, n_file, "application/pdf")

    # --- 2. FORM INSERIMENTO ---
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Nuova Sessione")
        with st.form("workout_form", clear_on_submit=True):
            f1, f2, f3 = st.columns(3)
            n_ins = f1.text_input("Nome *")
            c_ins = f2.text_input("Cognome *")
            s_ins = f3.selectbox("Sede *", ["Prati", "Corso Trieste"], index=None, placeholder="Seleziona Sede...")
            
            st.divider()
            f4, f5, f6, f7 = st.columns(4)
            d_ins = f4.date_input("Data *", value=None, format="DD/MM/YYYY")
            sess_sel = f5.selectbox("Sessione *", ["30 min", "45 min", "Altro..."], index=None, placeholder="Scegli...")
            prog_sel = f6.selectbox("Programma *", ["Forma", "Expert", "Sportivo", "Salute", "Manuale"], index=None, placeholder="Scegli...")
            liv_sel = f7.selectbox("Livello *", ["1-res", "2-res", "3-res", "1-var", "2-var", "3-var"], index=None, placeholder="Scegli...")
            
            st.divider()
            f8, f9, f10 = st.columns(3)
            v_ins = f8.number_input("Km/h *", min_value=0.0, step=0.1, value=0.0)
            k_ins = f9.number_input("Km totali *", min_value=0.0, step=0.1, value=0.0)
            cl_ins = f10.number_input("Calorie *", min_value=0, value=0)

            if st.form_submit_button("🚀 Salva Sessione"):
                if n_ins and c_ins and s_ins and d_ins and sess_sel and prog_sel and liv_sel:
                    client = get_gspread_client()
                    sheet = client.open_by_key(ID_FOGLIO).sheet1
                    riga = [f"{n_ins} {c_ins}", n_ins, c_ins, 0, "", d_ins.strftime("%d/%m/%Y"), sess_sel, prog_sel, liv_sel, v_ins, k_ins, cl_ins, s_ins, 0, 0, 0]
                    sheet.append_row(riga)
                    st.cache_data.clear()
                    st.success("Dati salvati!")
                    st.rerun()
                else:
                    st.error("Compila tutti i campi obbligatori!")

    # --- 3. ARCHIVIO (FILTRO ULTIMI 30 GIORNI) ---
    st.divider()
    st.subheader("📊 Gestione Archivio (Ultimi 30 giorni)")
    if dati_raw:
        df_glob = pd.DataFrame(dati_raw)
        df_glob.columns = [str(c).strip() for c in df_glob.columns]
        col_data_glob = get_col_name(df_glob.columns, ["DATA"], avoid=["NASCITA"])
        
        if col_data_glob:
            # Convertiamo la colonna data per il filtraggio
            df_glob[col_data_glob] = pd.to_datetime(df_glob[col_data_glob], dayfirst=True, errors='coerce')
            
            # Calcolo soglia temporale (Fuso Roma)
            tz_roma = pytz.timezone('Europe/Rome')
            oggi = datetime.now(tz_roma).replace(hour=0, minute=0, second=0, microsecond=0)
            limite_30gg = oggi - timedelta(days=30)
            
            # Applichiamo il filtro temporale
            df_recenti = df_glob[df_glob[col_data_glob] >= limite_30gg].copy()
            
            # Pulizia per la visualizzazione
            df_recenti_display = filtra_privacy(df_recenti)
            df_recenti_display[col_data_glob] = df_recenti_display[col_data_glob].dt.strftime('%d/%m/%Y')
            
            st.write(f"Record trovati dal {limite_30gg.strftime('%d/%m/%Y')}: {len(df_recenti_display)}")
            st.dataframe(df_recenti_display.iloc[::-1], use_container_width=True)

            with st.expander("🗑️ Cancella riga"):
                opzioni = []
                for idx, r in df_recenti.iterrows():
                    # Usiamo l'indice originale del DataFrame (+2 per riga Excel)
                    data_str = r[col_data_glob].strftime('%d/%m/%Y') if pd.notnull(r[col_data_glob]) else "N/D"
                    label = f"Riga {idx+2}: {r.get('Nome','')} {r.get('Cognome','')} - Data: {data_str}"
                    opzioni.append({"label": label, "idx": idx+2})
                
                sel = st.selectbox("Seleziona sessione:", opzioni[::-1], format_func=lambda x: x["label"], index=None, placeholder="Scegli...")
                if st.button("Conferma Eliminazione"):
                    if sel:
                        get_gspread_client().open_by_key(ID_FOGLIO).sheet1.delete_rows(sel["idx"])
                        st.cache_data.clear()
                        st.rerun()

except Exception as e:
    st.error(f"Errore: {e}")
