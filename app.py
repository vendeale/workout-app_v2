import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Workout Manager V2", page_icon="🚴‍♂️", layout="wide")

@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

try:
    client = get_gspread_client()
    # ID del tuo foglio Google
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4" 
    spreadsheet = client.open_by_key(ID_FOGLIO)
    sheet = spreadsheet.sheet1 

    st.title("🚴‍♂️ Registrazione Sessione Pedalata")

    with st.container(border=True):
        st.subheader("📝 Inserimento Dati Atleta e Sessione")
        
        with st.form("workout_form", clear_on_submit=True):
            # --- SEZIONE ANAGRAFICA ---
            st.markdown("##### 👤 Anagrafica")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                nome_cognome = st.text_input("Nome & Cognome")
            with c2:
                nome = st.text_input("Nome")
            with c3:
                cognome = st.text_input("Cognome")
            with c4:
                # DATA DI NASCITA: Opzionale e non pre-valorizzata
                data_nascita = st.date_input(
                    "Data di Nascita", 
                    value=None, 
                    min_value=datetime(1930, 1, 1), 
                    max_value=datetime.today(),
                    format="DD/MM/YYYY"
                )

            # --- SEZIONE SESSIONE ---
            st.divider()
            st.markdown("##### 📅 Dati Sessione")
            c5, c6, c7, c8 = st.columns(4)
            with c5:
                # DATA PEDALATA: Obbligatoria e non pre-valorizzata
                data_pedalata = st.date_input(
                    "Data Pedalata", 
                    value=None, 
                    format="DD/MM/YYYY"
                )
            with c6:
                sessione = st.text_input("Sessione")
            with c7:
                programma = st.text_input("Programma")
            with c8:
                # LIVELLO: Testo libero (accetta numeri e lettere)
                livello = st.text_input("Livello")

            # --- SEZIONE PERFORMANCE ---
            st.divider()
            st.markdown("##### 📈 Performance & Cuore")
            c9, c10, c11, c12 = st.columns(4)
            with c9:
                kmh = st.number_input("Km/h", min_value=0.0, step=0.1, value=0.0)
            with col10 := c10:
                km = st.number_input("Km totali", min_value=0.0, step=0.1, value=0.0)
            with col11 := c11:
                calorie = st.number_input("Calorie", min_value=0, step=1, value=0)
            with col12 := c12:
                # SEDI SPECIFICHE RICHIESTE
                sede = st.selectbox("Sede", ["", "Prati", "Corso Trieste"])

            c13, c14, c15, c16 = st.columns(4)
            with c13:
                fc_attuale = st.number_input("Frequenza cardiaca (attuale)", min_value=0, step=1, value=0)
            with c14:
                fc_min = st.number_input("FC Minima", min_value=0, step=1, value=0)
            with c15:
                fc_max = st.number_input("FC Massima", min_value=0, step=1, value=0)
            with c16:
                fc_media = st.number_input("FC Media", min_value=0, step=1, value=0)

            st.divider()
            submit = st.form_submit_button("🚀 Salva Dati Sessione")

            if submit:
                # Controllo mandatorio solo su Data Pedalata
                if data_pedalata is None:
                    st.error("⚠️ Errore: La 'Data Pedalata' è obbligatoria per il salvataggio!")
                else:
                    # Formattazione date in stringa per il foglio (GG/MM/AAAA)
                    data_nascita_str = data_nascita.strftime("%d/%m/%Y") if data_nascita else ""
                    data_pedalata_str = data_pedalata.strftime("%d/%m/%Y")

                    # Creazione riga (16 colonne totali)
                    nuova_riga = [
                        nome_cognome,   # A
                        nome,           # B
                        cognome,        # C
                        fc_attuale,     # D
                        data_nascita_str, # E
                        data_pedalata_str, # F
                        sessione,       # G
                        programma,      # H
                        livello,        # I
                        kmh,            # J
                        km,             # K
                        calorie,        # L
                        sede,           # M
                        fc_min,         # N
                        fc_max,         # O
                        fc_media        # P
                    ]
                    
                    sheet.append_row(nuova_riga)
                    st.success(f"✅ Sessione registrata con successo nel database!")
                    st.balloons()
                    st.cache_data.clear()

    # --- VISUALIZZAZIONE STORICO ---
    st.divider()
    st.subheader("📊 Ultime Sessioni Registrate")
    dati = sheet.get_all_records()
    if dati:
        df = pd.DataFrame(dati)
        # Mostra la tabella invertita (ultimo inserimento in alto)
        st.dataframe(df.iloc[::-1], use_container_width=True)
    else:
        st.info("Inizia a inserire dati per visualizzare lo storico.")

except Exception as e:
    st.error("Si è verificato un errore di comunicazione con il foglio Google.")
    if st.checkbox("Mostra Log Tecnico"):
        st.code(e)
