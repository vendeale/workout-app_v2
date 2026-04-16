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
        return sheet.get_all_records()
    except Exception as e:
        st.error(f"Errore di connessione a Google Sheets: {e}")
        return []

# --- HELPER: IDENTIFICAZIONE COLONNE DINAMICA ---
def get_col_name(columns, keywords, avoid=None):
    for col in columns:
        c_up = str(col).upper().strip()
        if any(key.upper() in c_up for key in keywords):
            if avoid and any(a.upper() in c_up for a in avoid):
                continue
            return col
    return None

# --- FUNZIONE GENERAZIONE PDF PROFESSIONALE ---
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
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, "RIEPILOGO SESSIONI RECENTI", 0, 1, 'L')
    
    # Tabella
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(230, 230, 230)
    w = [25, 45, 40, 20, 20, 25]
    headers = ["Data", "Programma", "Livello", "Km", "Km/h", "Calorie"]
    for i in range(len(headers)):
        pdf.cell(w[i], 8, headers[i], 1, 0, 'C', True)
    pdf.ln()

    pdf.set_font("Arial", '', 8)
    for _, row in df_atleta.iterrows():
        pdf.cell(w[0], 7, str(row.get(c_data, '')), 1, 0, 'C')
        pdf.cell(w[1], 7, str(row.get(c_prog, ''))[:22], 1, 0, 'L')
        pdf.cell(w[2], 7, str(row.get(c_liv, ''))[:20], 1, 0, 'L')
        pdf.cell(w[3], 7, str(row.get(c_km, '0')), 1, 0, 'C')
        pdf.cell(w[4], 7, str(row.get(c_kmh, '0')), 1, 0, 'C')
        pdf.cell(w[5], 7, str(row.get(c_cal, '0')), 1, 1, 'C')

    # Grafici
    plt.style.use('ggplot')
    df_plot = df_atleta.copy()
    for c in [c_km, c_kmh, c_cal]:
        if c: df_plot[c] = pd.to_numeric(df_plot[c], errors='coerce').fillna(0)

    fig, axs = plt.subplots(2, 2, figsize=(10, 8))
    plt.subplots_adjust(hspace=0.4, wspace=0.3)

    if c_km:
        axs[0, 0].plot(df_plot[c_data], df_plot[c_km], color='#00509E', marker='o')
        axs[0, 0].set_title('Km Percorsi', fontsize=10, fontweight='bold')
        axs[0, 0].tick_params(axis='x', rotation=45, labelsize=7)

    if c_kmh:
        axs[0, 1].bar(df_plot[c_data], df_plot[c_kmh], color='#FF8C00', alpha=0.7)
        axs[0, 1].set_title('Km/h Medi', fontsize=10, fontweight='bold')
        axs[0, 1].tick_params(axis='x', rotation=45, labelsize=7)

    if c_cal:
        axs[1, 0].fill_between(range(len(df_plot)), df_plot[c_cal], color='#2ECC71', alpha=0.3)
        axs[1, 0].set_title('Consumo Calorie', fontsize=10, fontweight='bold')

    axs[1, 1].axis('off')
    km_tot = df_plot[c_km].sum() if c_km else 0
    kmh_avg = df_plot[c_kmh].mean() if c_kmh else 0
    cal_avg = df_plot[c_cal].mean() if c_cal else 0
    res_text = f"STATISTICHE\n\nKm Totali: {km_tot:.1f}\nMedia Km/h: {kmh_avg:.1f}\nMedia Calorie: {cal_avg:.0f}"
    axs[1, 1].text(0.1, 0.5, res_text, fontsize=12, fontweight='bold', color='#1B4F72')

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=150, bbox_inches='tight')
    pdf.add_page()
    pdf.set_y(20)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "ANALISI GRAFICA PERFORMANCE", 0, 1, 'C')
    pdf.image(img_buf, x=10, y=35, w=190)
    plt.close(fig)
    
    return bytes(pdf.output())

# --- LOGICA APP ---
try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    dati_per_ricerca = fetch_all_data(ID_FOGLIO)

    st.markdown("<h2 style='text-align: center; color: #00509e;'>AQUATIME PERFORMANCE</h2>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- 1. RICERCA E REPORT ---
    st.divider()
    with st.expander("🔍 **RICERCA ATLETA E REPORT PDF**", expanded=False):
        c_search1, c_search2 = st.columns(2)
        with c_search1: s_nome = st.text_input("Nome:", key="sn")
        with c_search2: s_cognome = st.text_input("Cognome:", key="sc")
        
        if (s_nome or s_cognome) and dati_per_ricerca:
            df_tot = pd.DataFrame(dati_per_ricerca)
            df_tot.columns = [str(c).strip() for c in df_tot.columns]
            
            mask = (df_tot['Nome'].astype(str).str.contains(s_nome.strip(), case=False, na=False)) & \
                   (df_tot['Cognome'].astype(str).str.contains(s_cognome.strip(), case=False, na=False))
            
            risultati = df_tot[mask].copy()
            if not risultati.empty:
                col_data = get_col_name(risultati.columns, ["DATA"], avoid=["NASCITA"])
                if col_data:
                    risultati[col_data] = pd.to_datetime(risultati[col_data], dayfirst=True, errors='coerce')
                    risultati = risultati.sort_values(col_data)
                
                # Visualizzazione
                mostrare = [c for c in risultati.columns if not any(x in c.upper() for x in ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"])]
                df_display = risultati[mostrare].copy()
                if col_data: df_display[col_data] = df_display[col_data].dt.strftime('%d/%m/%Y')
                
                st.dataframe(df_display.iloc[::-1], use_container_width=True)

                pdf_file = generate_pdf(df_display, s_nome, s_cognome)
                st.download_button(label="📥 Scarica Report PDF", data=pdf_file, 
                                 file_name=f"Report_{s_nome}_{s_cognome}.pdf", mime="application/pdf")
            else:
                st.warning("Nessun risultato.")

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
    
    if dati_per_ricerca:
        df_glob = pd.DataFrame(dati_per_ricerca)
        df_glob.columns = [str(c).strip() for c in df_glob.columns]
        
        # Mostra le ultime 10 sessioni a video
        st.write("Ultime 10 sessioni inserite:")
        st.dataframe(df_glob.tail(10).iloc[::-1], use_container_width=True)

        # SEZIONE CANCELLA (Ripristinata)
        with st.expander("🗑️ **CANCELLA INSERIMENTO ERRATO**"):
            st.warning("Attenzione: l'eliminazione è irreversibile.")
            
            # Creiamo una lista di opzioni leggibili per la selectbox
            # Usiamo l'indice + 2 perché Google Sheets parte da 1 e la riga 1 è l'intestazione
            opzioni_delete = []
            col_d_p = get_col_name(df_glob.columns, ["DATA"], avoid=["NASCITA"]) or "Data Pedalata"
            
            for i, r in enumerate(dati_per_ricerca):
                label = f"Riga {i+2}: {r.get('Nome','')} {r.get('Cognome','')} - {r.get(col_d_p,'')}"
                opzioni_delete.append({"label": label, "index": i + 2})
            
            # Mostriamo le opzioni in ordine inverso (le più recenti in alto)
            scelta = st.selectbox("Seleziona la riga da rimuovere:", 
                                 options=opzioni_delete[::-1], 
                                 format_func=lambda x: x["label"])
            
            if st.button("Conferma Eliminazione"):
                client = get_gspread_client()
                sheet = client.open_by_key(ID_FOGLIO).sheet1
                sheet.delete_rows(scelta["index"])
                st.cache_data.clear()
                st.success(f"Riga {scelta['index']} eliminata correttamente!")
                st.rerun()

except Exception as e:
    st.error(f"Errore generale: {e}")
