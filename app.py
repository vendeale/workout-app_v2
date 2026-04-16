import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from fpdf import FPDF
import io

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Workout Manager V3", page_icon="🚴‍♂️", layout="wide")

# --- FUNZIONI DI ACCESSO AI DATI ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def fetch_all_data(id_foglio):
    client = get_gspread_client()
    spreadsheet = client.open_by_key(id_foglio)
    sheet = spreadsheet.sheet1
    return sheet.get_all_records()

# --- HELPER: IDENTIFICAZIONE COLONNE ---
def get_col_name(columns, keywords, avoid=None):
    for col in columns:
        c_up = str(col).upper().strip()
        if any(key.upper() in c_up for key in keywords):
            if avoid and any(a.upper() in c_up for a in avoid):
                continue
            return col
    return None

# --- FUNZIONE GENERAZIONE PDF ---
def generate_pdf(df_atleta, nome, cognome):
    pdf = FPDF()
    pdf.add_page()
    
    # Identificazione dinamica colonne
    c_data = get_col_name(df_atleta.columns, ["DATA"], avoid=["NASCITA"])
    c_km = get_col_name(df_atleta.columns, ["KM TOTALI", "KM PERCORSI"])
    c_kmh = get_col_name(df_atleta.columns, ["KM/H", "VELOCITA"])
    c_cal = get_col_name(df_atleta.columns, ["CALORIE", "KCAL"])
    c_prog = get_col_name(df_atleta.columns, ["PROGRAMMA"])
    c_liv = get_col_name(df_atleta.columns, ["LIVELLO"])

    # Intestazione
    pdf.set_font("Arial", 'B', 15)
    pdf.set_text_color(0, 80, 158) 
    pdf.cell(0, 10, "AQUATIME PERFORMANCE", 0, 1, 'L')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"REPORT PERFORMANCE: {nome.upper()} {cognome.upper()}", 0, 1, 'C')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, f"Data report: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'C')
    pdf.ln(10)

    # Tabella
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(230, 240, 255)
    pdf.cell(25, 8, "Data", 1, 0, 'C', True)
    pdf.cell(45, 8, "Programma", 1, 0, 'C', True)
    pdf.cell(30, 8, "Livello", 1, 0, 'C', True)
    pdf.cell(20, 8, "Km", 1, 0, 'C', True)
    pdf.cell(20, 8, "Km/h", 1, 0, 'C', True)
    pdf.cell(25, 8, "Calorie", 1, 1, 'C', True)

    pdf.set_font("Arial", '', 8)
    for _, row in df_atleta.iterrows():
        pdf.cell(25, 7, str(row.get(c_data, '')), 1)
        pdf.cell(45, 7, str(row.get(c_prog, ''))[:25], 1)
        pdf.cell(30, 7, str(row.get(c_liv, '')), 1)
        pdf.cell(20, 7, str(row.get(c_km, '0')), 1)
        pdf.cell(20, 7, str(row.get(c_kmh, '0')), 1)
        pdf.cell(25, 7, str(row.get(c_cal, '0')), 1)
        pdf.ln(0)

    # Grafici
    df_plot = df_atleta.copy()
    for c in [c_km, c_kmh, c_cal]:
        if c: df_plot[c] = pd.to_numeric(df_plot[c], errors='coerce').fillna(0)

    fig, axs = plt.subplots(2, 2, figsize=(10, 8))
    plt.subplots_adjust(hspace=0.4, wspace=0.3)
    
    # 1. Km
    if c_km:
        axs[0, 0].plot(df_plot[c_data], df_plot[c_km], color='#00509E', marker='o')
        axs[0, 0].set_title('Km per Sessione', fontsize=10, fontweight='bold')
        axs[0, 0].tick_params(axis='x', rotation=45, labelsize=7)
    
    # 2. Velocità
    if c_kmh:
        axs[0, 1].bar(df_plot[c_data], df_plot[c_kmh], color='#FF8C00')
        axs[0, 1].set_title('Km/h Medi', fontsize=10, fontweight='bold')
        axs[0, 1].tick_params(axis='x', rotation=45, labelsize=7)

    # 3. Calorie
    if c_cal:
        axs[1, 0].fill_between(range(len(df_plot)), df_plot[c_cal], color='#2ECC71', alpha=0.3)
        axs[1, 0].set_title('Andamento Calorie', fontsize=10, fontweight='bold')

    # 4. Statistiche
    axs[1, 1].axis('off')
    km_tot = df_plot[c_km].sum() if c_km else 0
    kmh_avg = df_plot[c_kmh].mean() if c_kmh else 0
    cal_avg = df_plot[c_cal].mean() if c_cal else 0
    txt = f"RIEPILOGO\n\nKm Totali: {km_tot:.1f}\nMedia Km/h: {kmh_avg:.1f}\nMedia Calorie: {cal_avg:.0f}"
    axs[1, 1].text(0.1, 0.5, txt, fontsize=12, fontweight='bold')

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=120)
    pdf.add_page()
    pdf.image(img_buf, x=10, y=30, w=190)
    plt.close(fig)
    
    # SOLUZIONE ALL'ERRORE BYTEARRAY: convertiamo in bytes
    return bytes(pdf.output())

try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    client = get_gspread_client()
    spreadsheet = client.open_by_key(ID_FOGLIO)
    sheet = spreadsheet.sheet1
    dati_per_ricerca = fetch_all_data(ID_FOGLIO)

    st.markdown("<h2 style='text-align: center; color: #00509e;'>AQUATIME PERFORMANCE</h2>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- RICERCA RAPIDA ---
    st.divider()
    with st.expander("🔍 **RICERCA RAPIDA ATLETA (Tutto l'archivio)**", expanded=False):
        c_search1, c_search2 = st.columns(2)
        with c_search1: s_nome = st.text_input("Nome:", key="sn")
        with c_search2: s_cognome = st.text_input("Cognome:", key="sc")
        
        if (s_nome or s_cognome) and dati_per_ricerca:
            df_tot = pd.DataFrame(dati_per_ricerca)
            df_tot.columns = [str(c).strip() for c in df_tot.columns]
            
            mask = pd.Series([True] * len(df_tot))
            if s_nome: mask &= df_tot['Nome'].astype(str).str.contains(s_nome.strip(), case=False, na=False)
            if s_cognome: mask &= df_tot['Cognome'].astype(str).str.contains(s_cognome.strip(), case=False, na=False)
            
            risultati = df_tot[mask].copy()
            if not risultati.empty:
                col_data = get_col_name(risultati.columns, ["DATA"], avoid=["NASCITA"])
                if col_data:
                    risultati[col_data] = pd.to_datetime(risultati[col_data], format='%d/%m/%Y', errors='coerce')
                    risultati = risultati.sort_values(col_data)
                
                mostrare = [c for c in risultati.columns if not any(x in c.upper() for x in ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"])]
                df_display = risultati[mostrare].copy()
                
                if col_data and col_data in df_display.columns:
                    df_display[col_data] = df_display[col_data].dt.strftime('%d/%m/%Y')
                
                st.success(f"Trovate {len(risultati)} sessioni")
                st.dataframe(df_display.iloc[::-1], use_container_width=True)

                # Generazione PDF
                pdf_output = generate_pdf(df_display, s_nome, s_cognome)
                st.download_button(
                    label="📥 Scarica Report Performance PDF",
                    data=pdf_output,
                    file_name=f"Report_{s_nome}_{s_cognome}.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("Nessun risultato.")

    # --- FORM INSERIMENTO ---
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Registra Nuova Sessione")
        with st.form("workout_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1: n_ins = st.text_input("Nome *")
            with c2: c_ins = st.text_input("Cognome *")
            with c3: s_ins = st.selectbox("Sede *", ["", "Prati", "Corso Trieste"])
            
            st.divider()
            col4, col5, col6, col7 = st.columns(4)
            with col4: d_ins = st.date_input("Data *", value=None, format="DD/MM/YYYY")
            with col5: s_sel = st.selectbox("Sessione *", ["", "30 min", "45 min", "Altro..."])
            with col6: p_sel = st.selectbox("Programma *", ["", "Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."])
            with col7: l_sel = st.selectbox("Livello *", ["", "1-res", "2-res", "3-res", "1-var", "2-var", "3-var", "Altro..."])

            st.divider()
            col8, col9, col10 = st.columns(3)
            with col8: v_ins = st.number_input("Km/h *", min_value=0.0, step=0.1)
            with col9: k_ins = st.number_input("Km totali *", min_value=0.0, step=0.1)
            with col10: cl_ins = st.number_input("Calorie *", min_value=0)

            if st.form_submit_button("🚀 Salva"):
                if not n_ins or not c_ins or not d_ins or not s_ins:
                    st.error("Campi obbligatori mancanti!")
                else:
                    row = [f"{n_ins} {c_ins}", n_ins, c_ins, 0, "", d_ins.strftime("%d/%m/%Y"), s_sel, p_sel, l_sel, v_ins, k_ins, cl_ins, s_ins, 0, 0, 0]
                    sheet.append_row(row)
                    st.cache_data.clear()
                    st.success("Dati salvati!")
                    st.rerun()

    # --- STORICO GLOBALE ---
    st.divider()
    st.subheader("📊 Ultime Sessioni (30gg)")
    if dati_per_ricerca:
        df_g = pd.DataFrame(dati_per_ricerca)
        df_g.columns = [str(c).strip() for c in df_g.columns]
        c_dat_g = get_col_name(df_g.columns, ["DATA"], avoid=["NASCITA"])
        if c_dat_g:
            df_g['dt'] = pd.to_datetime(df_g[c_dat_g], format='%d/%m/%Y', errors='coerce')
            df_f = df_g[df_g['dt'] >= (datetime.now() - timedelta(days=30))].copy()
            st.dataframe(df_f.iloc[::-1], use_container_width=True)

        with st.expander("🗑️ Cancella riga"):
            opzioni = [{"label": f"{r.get('Nome','')} {r.get('Cognome','')} - {r.get('Data Pedalata','')}", "idx": i+2} for i, r in enumerate(dati_per_ricerca)]
            sel = st.selectbox("Seleziona:", opzioni[::-1], format_func=lambda x: x["label"])
            if st.button("Elimina"):
                sheet.delete_rows(sel["idx"])
                st.cache_data.clear()
                st.rerun()

except Exception as e:
    st.error(f"Errore: {e}")
