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

# --- FUNZIONE GENERAZIONE PDF ---
def generate_pdf(df_atleta, nome, cognome):
    pdf = FPDF()
    pdf.add_page()
    
    # Logo Aquatime
    try:
        pdf.image("logo_aquatime.png", 10, 8, 40) # Cerca il file logo_aquatime.png
    except:
        pdf.set_font("Arial", 'B', 15)
        pdf.set_text_color(0, 80, 158) # Blu Aquatime
        pdf.cell(0, 10, "AQUATIME PERFORMANCE", 0, 1, 'L')
        pdf.set_text_color(0, 0, 0)

    # Intestazione e Data
    pdf.ln(15)
    pdf.set_font("Arial", 'B', 18)
    pdf.cell(0, 10, f"REPORT ATLETA: {nome.upper()} {cognome.upper()}", 0, 1, 'C')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, f"Generato il: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'C')
    pdf.ln(10)

    # Tabella Sessioni
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Riepilogo Sessioni:", 0, 1, 'L')
    pdf.set_font("Arial", '', 9)
    
    # Intestazioni Tabella
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(25, 8, "Data", 1, 0, 'C', True)
    pdf.cell(40, 8, "Programma", 1, 0, 'C', True)
    pdf.cell(30, 8, "Livello", 1, 0, 'C', True)
    pdf.cell(20, 8, "Km", 1, 0, 'C', True)
    pdf.cell(20, 8, "Km/h", 1, 0, 'C', True)
    pdf.cell(25, 8, "Calorie", 1, 1, 'C', True)

    for _, row in df_atleta.iterrows():
        pdf.cell(25, 7, str(row['Data Pedalata']), 1)
        pdf.cell(40, 7, str(row['Programma'])[:22], 1)
        pdf.cell(30, 7, str(row['Livello']), 1)
        pdf.cell(20, 7, str(row['Km totali']), 1)
        pdf.cell(20, 7, str(row['Km/h']), 1)
        pdf.cell(25, 7, str(row['Calorie']), 1)
        pdf.ln(0)

    # Calcolo Medie per Grafici
    avg_cal = df_atleta['Calorie'].mean()
    avg_kmh = df_atleta['Km/h'].mean()
    total_km = df_atleta['Km totali'].sum()
    avg_km = df_atleta['Km totali'].mean()

    # Creazione Grafici
    plt.style.use('seaborn-v0_8-muted') # Stile pulito
    fig, axs = plt.subplots(2, 2, figsize=(10, 8))
    plt.subplots_adjust(hspace=0.4, wspace=0.3)

    # 1. Km Totali (Andamento)
    axs[0, 0].plot(df_atleta['Data Pedalata'], df_atleta['Km totali'], color='#00509E', marker='o', linewidth=2)
    axs[0, 0].set_title(f'Km Percorsi (Tot: {total_km:.1f})', fontsize=10, fontweight='bold')
    axs[0, 0].tick_params(axis='x', rotation=45, labelsize=8)

    # 2. Velocità Media
    axs[0, 1].bar(df_atleta['Data Pedalata'], df_atleta['Km/h'], color='#FF8C00')
    axs[0, 1].axhline(y=avg_kmh, color='red', linestyle='--', label=f'Media: {avg_kmh:.1f}')
    axs[0, 1].set_title('Km/h Medi per Sessione', fontsize=10, fontweight='bold')
    axs[0, 1].tick_params(axis='x', rotation=45, labelsize=8)
    axs[0, 1].legend(fontsize=7)

    # 3. Calorie (Andamento)
    axs[1, 0].fill_between(df_atleta['Data Pedalata'], df_atleta['Calorie'], color='#2ECC71', alpha=0.3)
    axs[1, 0].plot(df_atleta['Data Pedalata'], df_atleta['Calorie'], color='#27AE60', marker='s')
    axs[1, 0].set_title(f'Calorie (Media: {avg_cal:.0f})', fontsize=10, fontweight='bold')
    axs[1, 0].tick_params(axis='x', rotation=45, labelsize=8)

    # 4. Confronto Km vs Media
    axs[1, 1].bar(['Media Atleta', 'Totale Km'], [avg_km, total_km/10], color=['#3498DB', '#34495E']) # Diviso 10 per scala
    axs[1, 1].set_title('Proporzione Performance', fontsize=10, fontweight='bold')

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=150, bbox_inches='tight')
    img_buf.seek(0)
    
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Analisi Performance Grafica", 0, 1, 'L')
    pdf.image(img_buf, x=10, y=30, w=190)
    
    plt.close(fig)
    return pdf.output()

try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    client = get_gspread_client()
    spreadsheet = client.open_by_key(ID_FOGLIO)
    sheet = spreadsheet.sheet1
    dati_per_ricerca = fetch_all_data(ID_FOGLIO)

    # --- LOGO E TITOLO ---
    col_l, col_logo, col_r = st.columns([2, 1, 2])
    with col_logo:
        try:
            st.image("logo_aquatime.png", use_container_width=True)
        except:
            st.markdown("<h2 style='text-align: center; color: #00509e;'>AQUATIME</h2>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- RICERCA RAPIDA ---
    st.divider()
    with st.expander("🔍 **RICERCA RAPIDA ATLETA (Tutto l'archivio)**", expanded=False):
        c_search1, c_search2 = st.columns(2)
        with c_search1: search_nome = st.text_input("Nome:", key="s_nome")
        with c_search2: search_cognome = st.text_input("Cognome:", key="s_cognome")
        
        if (search_nome or search_cognome) and dati_per_ricerca:
            df_totale = pd.DataFrame(dati_per_ricerca)
            df_totale.columns = [str(c).strip() for c in df_totale.columns]
            
            mask = pd.Series([True] * len(df_totale))
            if search_nome: mask &= df_totale['Nome'].astype(str).str.contains(search_nome.strip(), case=False, na=False)
            if search_cognome: mask &= df_totale['Cognome'].astype(str).str.contains(search_cognome.strip(), case=False, na=False)
            
            risultati = df_totale[mask].copy()
            if not risultati.empty:
                # Pulizia per display
                risultati['Data Pedalata'] = pd.to_datetime(risultati['Data Pedalata'], format='%d/%m/%Y', errors='coerce')
                risultati = risultati.sort_values('Data Pedalata')
                
                parole_no = ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"]
                col_mostrare = [c for c in risultati.columns if not any(x in c.upper() for x in parole_no)]
                
                df_display = risultati[col_mostrare].copy()
                df_display['Data Pedalata'] = df_display['Data Pedalata'].dt.strftime('%d/%m/%Y')
                
                st.success(f"Trovate {len(risultati)} sessioni")
                st.dataframe(df_display.iloc[::-1], use_container_width=True)

                # Generazione PDF
                pdf_bytes = generate_pdf(df_display, search_nome, search_cognome)
                st.download_button(
                    label="📥 Scarica Report Performance PDF",
                    data=pdf_bytes,
                    file_name=f"Report_Aquatime_{search_nome}_{search_cognome}.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("Nessun risultato trovato.")

    # --- FORM INSERIMENTO (CODICE PRECEDENTE) ---
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Registra Nuova Sessione")
        with st.form("workout_form", clear_on_submit=True):
            st.markdown("##### 👤 Atleta")
            c1, c2, c_sede = st.columns([1, 1, 1])
            with c1: n_i = st.text_input("Nome *")
            with c2: c_i = st.text_input("Cognome *")
            with c_sede: s_i = st.selectbox("Sede *", ["", "Prati", "Corso Trieste"])

            st.divider()
            st.markdown("##### 📅 Sessione e Programma")
            c4, c5, c6, c7 = st.columns(4)
            with c4: d_i = st.date_input("Data Pedalata *", value=None, format="DD/MM/YYYY")
            with c5:
                l_s = ["", "30 min", "45 min", "Altro..."]
                s_sel = st.selectbox("Sessione *", options=l_s)
                s_ex = st.text_input("Se 'Altro', specifica:")
            with c6:
                l_p = ["", "Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."]
                p_sel = st.selectbox("Programma *", options=l_p)
                p_ex = st.text_input("Se 'Altro', specifica:")
            with c7:
                l_l = ["", "1-resistenza", "2-resistenza", "3-resistenza", "1-variabile", "2-variabile", "3-variabile", "4-variabile", "5-variabile", "6-variabile", "Altro..."]
                lv_sel = st.selectbox("Livello *", options=l_l)
                lv_ex = st.text_input("Se 'Altro', specifica:")

            st.divider()
            st.markdown("##### 📈 Performance")
            c8, c9, c10 = st.columns(3)
            with c8: v_i = st.number_input("Km/h *", min_value=0.0, step=0.1)
            with c9: k_i = st.number_input("Km totali *", min_value=0.0, step=0.1)
            with c10: cl_i = st.number_input("Calorie *", min_value=0)

            if st.form_submit_button("🚀 Salva"):
                p_f = p_ex if p_sel == "Altro..." else p_sel
                s_f = s_ex if s_sel == "Altro..." else s_sel
                lv_f = lv_ex if lv_sel == "Altro..." else lv_sel
                
                if not n_i or not c_i or not d_i or not p_f or not s_f or not lv_f or not s_i:
                    st.error("⚠️ Compila i campi obbligatori!")
                else:
                    row = [f"{n_i} {c_i}", n_i, c_i, 0, "", d_i.strftime("%d/%m/%Y"), s_f, p_f, lv_f, v_i, k_i, cl_i, s_i, 0, 0, 0]
                    sheet.append_row(row)
                    st.success("Dati salvati!")
                    st.cache_data.clear()
                    st.rerun()

    # --- STORICO GLOBALE (ORDINATO) ---
    st.divider()
    st.subheader("📊 Ultime Sessioni Globali (30gg)")
    if dati_per_ricerca:
        df_g = pd.DataFrame(dati_per_ricerca)
        df_g.columns = [str(c).strip() for c in df_g.columns]
        try:
            df_g['Data_dt'] = pd.to_datetime(df_g['Data Pedalata'], format='%d/%m/%Y', errors='coerce')
            df_f = df_g[df_g['Data_dt'] >= (datetime.now() - timedelta(days=30))].copy()
            mostrare = [c for c in df_f.columns if not any(w in c.upper() for w in ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"])]
            st.dataframe(df_f[mostrare].iloc[::-1], use_container_width=True)
        except:
            st.write("Errore nel caricamento grafico storico.")

        with st.expander("🗑️ Cancella inserimento errato"):
            opzioni = [{"label": f"{r.get('Nome','')} {r.get('Cognome','')} - {r.get('Data Pedalata','')}", "idx": i+2} for i, r in enumerate(dati_per_ricerca)]
            if opzioni:
                sel = st.selectbox("Seleziona riga:", opzioni[::-1], format_func=lambda x: x["label"])
                if st.button("Elimina"):
                    sheet.delete_rows(sel["idx"])
                    st.cache_data.clear()
                    st.rerun()

except Exception as e:
    st.error("Errore di connessione o configurazione.")
    st.exception(e)
