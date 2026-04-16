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
    
    # Intestazione Testuale Aquatime
    pdf.set_font("Arial", 'B', 15)
    pdf.set_text_color(0, 80, 158) 
    pdf.cell(0, 10, "AQUATIME PERFORMANCE", 0, 1, 'L')
    pdf.set_text_color(0, 0, 0)

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 18)
    pdf.cell(0, 10, f"REPORT ATLETA: {nome.upper()} {cognome.upper()}", 0, 1, 'C')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, f"Generato il: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'C')
    pdf.ln(10)

    # Tabella Sessioni
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, "Riepilogo Sessioni:", 0, 1, 'L')
    pdf.set_font("Arial", '', 9)
    
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(25, 8, "Data", 1, 0, 'C', True)
    pdf.cell(45, 8, "Programma", 1, 0, 'C', True)
    pdf.cell(30, 8, "Livello", 1, 0, 'C', True)
    pdf.cell(20, 8, "Km", 1, 0, 'C', True)
    pdf.cell(20, 8, "Km/h", 1, 0, 'C', True)
    pdf.cell(25, 8, "Calorie", 1, 1, 'C', True)

    for _, row in df_atleta.iterrows():
        pdf.cell(25, 7, str(row['Data Pedalata']), 1)
        pdf.cell(45, 7, str(row['Programma'])[:25], 1)
        pdf.cell(30, 7, str(row['Livello']), 1)
        pdf.cell(20, 7, str(row['Km totali']), 1)
        pdf.cell(20, 7, str(row['Km/h']), 1)
        pdf.cell(25, 7, str(row['Calorie']), 1)
        pdf.ln(0)

    # Grafici
    df_atleta['Km totali'] = pd.to_numeric(df_atleta['Km totali'], errors='coerce')
    df_atleta['Km/h'] = pd.to_numeric(df_atleta['Km/h'], errors='coerce')
    df_atleta['Calorie'] = pd.to_numeric(df_atleta['Calorie'], errors='coerce')

    fig, axs = plt.subplots(2, 2, figsize=(10, 8))
    plt.subplots_adjust(hspace=0.4, wspace=0.3)

    # 1. Km
    axs[0, 0].plot(df_atleta['Data Pedalata'], df_atleta['Km totali'], color='#00509E', marker='o')
    axs[0, 0].set_title('Andamento Distanza (Km)', fontsize=10, fontweight='bold')
    axs[0, 0].tick_params(axis='x', rotation=45, labelsize=7)

    # 2. Velocità
    axs[0, 1].bar(df_atleta['Data Pedalata'], df_atleta['Km/h'], color='#FF8C00')
    axs[0, 1].set_title('Velocità Media (Km/h)', fontsize=10, fontweight='bold')
    axs[0, 1].tick_params(axis='x', rotation=45, labelsize=7)

    # 3. Calorie
    axs[1, 0].fill_between(df_atleta['Data Pedalata'], df_atleta['Calorie'], color='#2ECC71', alpha=0.3)
    axs[1, 0].set_title('Consumo Calorico', fontsize=10, fontweight='bold')
    axs[1, 0].tick_params(axis='x', rotation=45, labelsize=7)

    # 4. Boxplot per distribuzione
    axs[1, 1].boxplot(df_atleta['Km totali'].dropna())
    axs[1, 1].set_title('Variabilità Distanza', fontsize=10, fontweight='bold')

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=150, bbox_inches='tight')
    img_buf.seek(0)
    
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Analisi Grafica Performance", 0, 1, 'L')
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
    st.markdown("<h2 style='text-align: center; color: #00509e;'>AQUATIME</h2>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- RICERCA RAPIDA ---
    st.divider()
    with st.expander("🔍 **RICERCA RAPIDA ATLETA (Tutto l'archivio)**", expanded=False):
        c_search1, c_search2 = st.columns(2)
        with c_search1: s_nome = st.text_input("Filtra Nome:", key="search_n")
        with c_search2: s_cognome = st.text_input("Filtra Cognome:", key="search_c")
        
        if (s_nome or s_cognome) and dati_per_ricerca:
            df_totale = pd.DataFrame(dati_per_ricerca)
            df_totale.columns = [str(c).strip() for c in df_totale.columns]
            
            mask = pd.Series([True] * len(df_totale))
            if s_nome: mask &= df_totale['Nome'].astype(str).str.contains(s_nome.strip(), case=False, na=False)
            if s_cognome: mask &= df_totale['Cognome'].astype(str).str.contains(s_cognome.strip(), case=False, na=False)
            
            risultati = df_totale[mask].copy()
            if not risultati.empty:
                risultati['Data Pedalata'] = pd.to_datetime(risultati['Data Pedalata'], format='%d/%m/%Y', errors='coerce')
                risultati = risultati.sort_values('Data Pedalata')
                
                parole_no = ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"]
                col_mostrare = [c for c in risultati.columns if not any(x in c.upper() for x in parole_no)]
                
                df_display = risultati[col_mostrare].copy()
                df_display['Data Pedalata'] = df_display['Data Pedalata'].dt.strftime('%d/%m/%Y')
                
                st.success(f"Trovate {len(risultati)} sessioni")
                st.dataframe(df_display.iloc[::-1], use_container_width=True)

                pdf_bytes = generate_pdf(df_display, s_nome, s_cognome)
                st.download_button(
                    label="📥 Scarica Report Performance PDF",
                    data=pdf_bytes,
                    file_name=f"Report_Aquatime_{s_nome}_{s_cognome}.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("Nessun risultato trovato.")

    # --- FORM INSERIMENTO ---
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Registra Nuova Sessione")
        with st.form("workout_form", clear_on_submit=True):
            st.markdown("##### 👤 Atleta")
            c1, c2, c_sede = st.columns([1, 1, 1])
            with c1: n_ins = st.text_input("Nome *")
            with c2: c_ins = st.text_input("Cognome *")
            with c_sede: s_ins = st.selectbox("Sede *", ["", "Prati", "Corso Trieste"])

            st.divider()
            st.markdown("##### 📅 Sessione e Programma")
            col4, col5, col6, col7 = st.columns(4)
            with col4: d_ins = st.date_input("Data Pedalata *", value=None, format="DD/MM/YYYY")
            with col5:
                s_sel = st.selectbox("Sessione *", options=["", "30 min", "45 min", "Altro..."])
                s_ex = st.text_input("Specifica sessione se 'Altro':", key="ex_sess")
            with col6:
                p_sel = st.selectbox("Programma *", options=["", "Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."])
                p_ex = st.text_input("Specifica programma se 'Altro':", key="ex_prog")
            with col7:
                lv_sel = st.selectbox("Livello *", options=["", "1-resistenza", "2-resistenza", "3-resistenza", "1-variabile", "2-variabile", "3-variabile", "4-variabile", "5-variabile", "6-variabile", "Altro..."])
                lv_ex = st.text_input("Specifica livello se 'Altro':", key="ex_liv")

            st.divider()
            st.markdown("##### 📈 Performance")
            col8, col9, col10 = st.columns(3)
            with col8: v_ins = st.number_input("Km/h *", min_value=0.0, step=0.1)
            with col9: k_ins = st.number_input("Km totali *", min_value=0.0, step=0.1)
            with col10: cl_ins = st.number_input("Calorie *", min_value=0)

            submitted = st.form_submit_button("🚀 Salva Sessione")

            if submitted:
                p_final = p_ex if p_sel == "Altro..." else p_sel
                s_final = s_ex if s_sel == "Altro..." else s_sel
                lv_final = lv_ex if lv_sel == "Altro..." else lv_sel
                
                if not n_ins or not c_ins or not d_ins or not p_final or not s_final or not lv_final or not s_ins:
                    st.error("⚠️ Compila i campi obbligatori!")
                else:
                    row = [f"{n_ins} {c_ins}", n_ins, c_ins, 0, "", d_ins.strftime("%d/%m/%Y"), s_final, p_final, lv_final, v_ins, k_ins, cl_ins, s_ins, 0, 0, 0]
                    sheet.append_row(row)
                    st.success("Dati salvati!")
                    st.cache_data.clear()
                    st.rerun()

    # --- STORICO GLOBALE ---
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
            st.info("Caricamento storico...")

        with st.expander("🗑️ Cancella inserimento errato"):
            opzioni = [{"label": f"{r.get('Nome','')} {r.get('Cognome','')} - {r.get('Data Pedalata','')}", "idx": i+2} for i, r in enumerate(dati_per_ricerca)]
            if opzioni:
                sel = st.selectbox("Seleziona riga:", opzioni[::-1], format_func=lambda x: x["label"])
                if st.button("Elimina definitivamente"):
                    sheet.delete_rows(sel["idx"])
                    st.cache_data.clear()
                    st.rerun()

except Exception as e:
    st.error("Errore di configurazione.")
    st.exception(e)
