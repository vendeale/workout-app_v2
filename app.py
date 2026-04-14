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
                # Impostato formato visualizzazione nel widget
                data_nascita = st.date_input("Data di Nascita", min_value=datetime(1930, 1, 1), format="DD/MM/YYYY")

            # --- SEZIONE SESSIONE ---
            st.divider()
            st.markdown("##### 📅 Dati Sessione")
            c5, c6, c7, c8 = st.columns(4)
            with c5:
                data_pedalata = st.date_input("Data Pedalata", format="DD/MM/YYYY")
            with c6:
                sessione = st.text_input("Sessione")
            with c7:
                programma = st.text_input("Programma")
            with c8:
                livello = st.number_input("Livello", min_value=0, step=1)

            # --- SEZIONE PERFORMANCE ---
            st.divider()
            st.markdown("##### 📈 Performance & Cuore")
            c9, c10, c11, c12 = st.columns(4)
            with c9:
                kmh = st.number_input("Km/h", min_value=0.0, step=0.1)
            with c10:
                km = st.number_input("Km totali", min_value=0.0, step=0.1)
            with c11:
                calorie = st.number_input("Calorie", min_value=0, step=1)
            with c12:
                sede = st.selectbox("Sede", ["Sede 1", "Sede 2", "Sede 3"])

            c13, c14, c15, c16 = st.columns(4)
            with c13:
                fc_attuale = st.number_input("Frequenza cardiaca (attuale)", min_value=0, step=1)
            with c14:
                fc_min = st.number_input("FC Minima", min_value=0, step=1)
            with c15:
                fc_max = st.number_input("FC Massima", min_value=0, step=1)
            with c16:
                fc_media = st.number_input("FC Media", min_value=0, step=1)

            st.divider()
            submit = st.form_submit_button("🚀 Salva Dati Sessione")

            if submit:
                # Conversione date in formato GG/MM/AAAA per il foglio Google
                data_nascita_str = data_nascita.strftime("%d/%m/%Y")
                data_pedalata_str = data_pedalata.strftime("%d/%m/%Y")

                # ⚠️ MAPPA DELLE 16 COLONNE (A -> P)
                nuova_riga = [
                    nome_cognome,               # A
                    nome,                       # B
                    cognome,                    # C
                    fc_attuale,                 # D
                    data_nascita_str,           # E (Formato GG/MM/AAAA)
                    data_pedalata_str,          # F (Formato GG/MM/AAAA)
                    sessione,                   # G
                    programma,                  # H
                    livello,                    # I
                    kmh,                        # J
                    km,                         # K
                    calorie,                    # L
                    sede,                       # M
                    fc_min,                     # N
                    fc_max,                     # O
                    fc_media                    # P
                ]
                
                sheet.append_row(nuova_riga)
                st.success(f"✅ Sessione di {nome_cognome} registrata il {data_pedalata_str}!")
                st.balloons()
                st.cache_data.clear()

    # --- VISUALIZZAZIONE ---
    st.divider()
    st.subheader("📊 Ultime Sessioni Registrate")
    dati = sheet.get_all_records()
    if dati:
        df = pd.DataFrame(dati)
        st.dataframe(df.iloc[::-1], use_container_width=True)

except Exception as e:
    st.error("Errore durante l'operazione.")
    st.code(e)
