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
    
    # 3) Logo (Se presente, altrimenti testo)
    try:
        pdf.image("logo.png", 10, 8, 33) # Assicurati che logo.png esista o rinominalo
    except:
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "AQUATIME PERFORMANCE", 0, 1, 'L')

    # 1) & 2) Intestazione
    pdf.set_font("Arial", 'B', 16)
    pdf.ln(10)
    pdf.cell(0, 10, f"REPORT PERFORMANCE: {nome.upper()} {cognome.upper()}", 0, 1, 'C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Data produzione report: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'C')
    pdf.ln(10)

    # 4) Tabella Allenamenti
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 10, "Storico Allenamenti:", 0, 1, 'L')
    pdf.set_font("Arial", '', 8)
    
    # Intestazioni tabella
    col_width = 30
    pdf.cell(25, 8, "Data", 1)
    pdf.cell(35, 8, "Programma", 1)
    pdf.cell(30, 8, "Livello", 1)
    pdf.cell(20, 8, "Km", 1)
    pdf.cell(20, 8, "Km/h", 1)
    pdf.cell(25, 8, "Calorie", 1)
    pdf.ln()

    for i, row in df_atleta.iterrows():
        pdf.cell(25, 7, str(row['Data Pedalata']), 1)
        pdf.cell(35, 7, str(row['Programma'])[:20], 1)
        pdf.cell(30, 7, str(row['Livello']), 1)
        pdf.cell(20, 7, str(row['Km totali']), 1)
        pdf.cell(20, 7, str(row['Km/h']), 1)
        pdf.cell(25, 7, str(row['Calorie']), 1)
        pdf.ln()

    # 5) Grafici
    # Creiamo i grafici con Matplotlib
    fig, axs = plt.subplots(2, 2, figsize=(10, 8))
    plt.subplots_adjust(hspace=0.4, wspace=0.3)
    
    # Grafico Km Totali
    axs[0, 0].plot(df_atleta['Data Pedalata'], df_atleta['Km totali'], color='blue', marker='o')
    axs[0, 0].set_title('Km Totali per Sessione')
    axs[0, 0].tick_params(axis='x', rotation=45)

    # Grafico Km/h Medi
    axs[0, 1].bar(df_atleta['Data Pedalata'], df_atleta['Km/h'], color='orange')
    axs[0, 1].set_title('Velocità Media (Km/h)')
    axs[0, 1].tick_params(axis='x', rotation=45)

    # Grafico Calorie
    axs[1, 0].plot(df_atleta['Data Pedalata'], df_atleta['Calorie'], color='green', linestyle='--')
    axs[1, 0].set_title('Calorie Consumate')
    axs[1, 0].tick_params(axis='x', rotation=45)

    # Grafico Distribuzione Km
    axs[1, 1].hist(df_atleta['Km totali'], bins=5, color='purple', alpha=0.7)
    axs[1, 1].set_title('Distribuzione Distanze')

    # Salvataggio grafico in un buffer
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png')
    img_buf.seek(0)
    
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Analisi Grafica Performance", 0, 1, 'L')
    pdf.image(img_buf, x=10, y=30, w=190)
    
    return pdf.output()

try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    client = get_gspread_client()
    spreadsheet = client.open_by_key(ID_FOGLIO)
    sheet = spreadsheet.sheet1

    dati_per_ricerca = fetch_all_data(ID_FOGLIO)

    # --- INTESTAZIONE ---
    col_l, col_logo, col_r = st.columns([2, 1, 2])
    with col_logo:
        try:
            st.image("logo.png", use_container_width=True)
        except:
            st.markdown("<h3 style='text-align: center; color: #ff4b4b;'>Richards Fitness</h3>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- SEZIONE: RICERCA RAPIDA ATLETA ---
    st.divider()
    with st.expander("🔍 **RICERCA RAPIDA ATLETA (Tutto l'archivio)**", expanded=False):
        c_search1, c_search2 = st.columns(2)
        with c_search1:
            search_nome = st.text_input("Filtra per Nome:", placeholder="Es. Mario")
        with c_search2:
            search_cognome = st.text_input("Filtra per Cognome:", placeholder="Es. Rossi")
        
        if (search_nome or search_cognome) and dati_per_ricerca:
            df_totale = pd.DataFrame(dati_per_ricerca)
            df_totale.columns = [str(c).strip() for c in df_totale.columns]
            
            mask = pd.Series([True] * len(df_totale))
            if search_nome:
                mask &= df_totale['Nome'].astype(str).str.contains(search_nome.strip(), case=False, na=False)
            if search_cognome:
                mask &= df_totale['Cognome'].astype(str).str.contains(search_cognome.strip(), case=False, na=False)
            
            risultati = df_totale[mask].copy()
            if not risultati.empty:
                st.success(f"Trovate {len(risultati)} sessioni per {search_nome} {search_cognome}")
                
                # Ordinamento per data per i grafici
                risultati['Data Pedalata'] = pd.to_datetime(risultati['Data Pedalata'], format='%d/%m/%Y', errors='coerce')
                risultati = risultati.sort_values('Data Pedalata')
                
                # Visualizzazione tabella filtrata
                parole_escludere = ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"]
                col_mostrare = [c for c in risultati.columns if not any(x in c.upper() for x in parole_escludere)]
                
                # Trasformiamo la data in stringa per la visualizzazione corretta
                df_display = risultati[col_mostrare].copy()
                df_display['Data Pedalata'] = df_display['Data Pedalata'].dt.strftime('%d/%m/%Y')
                st.dataframe(df_display.iloc[::-1], use_container_width=True)

                # --- PULSANTE GENERAZIONE PDF ---
                st.markdown("---")
                pdf_bytes = generate_pdf(df_display, search_nome, search_cognome)
                st.download_button(
                    label="📥 Scarica Report Performance PDF",
                    data=pdf_bytes,
                    file_name=f"Report_{search_nome}_{search_cognome}.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("Nessun risultato trovato.")

    # --- MASCHERA DI INSERIMENTO ---
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Registra Nuova Sessione")
        with st.form("workout_form", clear_on_submit=True):
            st.markdown("##### 👤 Atleta")
            c1, c2, c_sede = st.columns([1, 1, 1])
            with c1: nome_ins = st.text_input("Nome *")
            with c2: cognome_ins = st.text_input("Cognome *")
            with c_sede: sede_ins = st.selectbox("Sede *", ["", "Prati", "Corso Trieste"])

            st.divider()
            st.markdown("##### 📅 Sessione e Programma")
            c4, c5, c6, c7 = st.columns(4)
            with c4: data_ped_ins = st.date_input("Data Pedalata *", value=None, format="DD/MM/YYYY")
            with c5:
                lista_s = ["", "30 min", "45 min", "Altro..."]
                sess_sel = st.selectbox("Sessione *", options=lista_s)
                sess_extra = st.text_input("Se 'Altro', specifica durata:")
            with c6:
                lista_p = ["", "Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."]
                prog_sel = st.selectbox("Programma *", options=lista_p)
                prog_extra = st.text_input("Se 'Altro', specifica programma:")
            with c7:
                lista_l = ["", "1-resistenza", "2-resistenza", "3-resistenza", "1-variabile", "2-variabile", "3-variabile", "4-variabile", "5-variabile", "6-variabile", "Altro..."]
                liv_sel = st.selectbox("Livello *", options=lista_l)
                liv_extra = st.text_input("Se 'Altro', specifica livello:")

            st.divider()
            st.markdown("##### 📈 Performance")
            c8, c9, c10 = st.columns(3)
            with c8: kmh_ins = st.number_input("Km/h *", min_value=0.0, step=0.1)
            with c9: km_ins = st.number_input("Km totali *", min_value=0.0, step=0.1)
            with c10: cal_ins = st.number_input("Calorie *", min_value=0)

            submit = st.form_submit_button("🚀 Salva Sessione")

            if submit:
                prog_f = prog_extra if prog_sel == "Altro..." else prog_sel
                sess_f = sess_extra if sess_sel == "Altro..." else sess_sel
                liv_f = liv_extra if liv_sel == "Altro..." else liv_sel
                
                if not nome_ins or not cognome_ins or not data_ped_ins or not prog_f or not sess_f or not liv_f or not sede_ins:
                    st.error("⚠️ Compila i campi obbligatori!")
                else:
                    nome_completo = f"{nome_ins} {cognome_ins}".strip()
                    row = [
                        nome_completo, nome_ins, cognome_ins, 0, "", 
                        data_ped_ins.strftime("%d/%m/%Y"), sess_f, prog_f, 
                        liv_f, kmh_ins, km_ins, cal_ins, sede_ins, 0, 0, 0
                    ]
                    sheet.append_row(row)
                    st.success("Dati salvati!")
                    st.cache_data.clear() 
                    st.rerun()

    # --- STORICO GLOBALE ---
    st.divider()
    st.subheader("📊 Ultime Sessioni Globali (Ultimi 30 giorni)")
    
    if dati_per_ricerca:
        df_g = pd.DataFrame(dati_per_ricerca)
        df_g.columns = [str(c).strip() for c in df_g.columns]
        
        try:
            df_g['Data_dt'] = pd.to_datetime(df_g['Data Pedalata'], format='%d/%m/%Y', errors='coerce')
            limite = datetime.now() - timedelta(days=30)
            df_f = df_g[df_g['Data_dt'] >= limite].copy()
            
            parole_escludere = ["FREQUENZA", "CARDIACA", "FC", "NASCITA", "DT"]
            mostrare = [c for c in df_f.columns if not any(word in c.upper() for word in parole_escludere)]
            
            if not df_f.empty:
                st.dataframe(df_f[mostrare].iloc[::-1], use_container_width=True)
            else:
                st.info("Nessuna sessione negli ultimi 30 giorni.")
        except:
            mostrare = [c for c in df_g.columns if not any(word in c.upper() for word in ["FREQUENZA", "CARDIACA", "FC", "NASCITA"])]
            st.dataframe(df_g[mostrare].iloc[::-1], use_container_width=True)

        with st.expander("🗑️ Cancella inserimento errato"):
            opzioni = [{"label": f"{r.get('Nome', '')} {r.get('Cognome', '')} - {r.get('Data Pedalata', '')}", "idx": i+2} for i, r in enumerate(dati_per_ricerca)]
            if opzioni:
                opzioni_invertite = opzioni[::-1]
                sel = st.selectbox("Seleziona riga:", opzioni_invertite, format_func=lambda x: x["label"])
                if st.button("Elimina definitivamente"):
                    sheet.delete_rows(sel["idx"])
                    st.cache_data.clear()
                    st.rerun()
    else:
        st.info("Nessun dato presente.")

except Exception as e:
    st.error("Errore critico.")
    st.exception(e)
