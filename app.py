import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")

# --- CONNESSIONE GOOGLE SHEETS ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    # Carica le credenziali dai Secrets di Streamlit
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

try:
    client = get_gspread_client()
    
    # ⚠️ INCOLLA QUI IL NOME ESATTO DEL TUO FILE GOOGLE SHEETS
    NOME_FILE = "https://docs.google.com/spreadsheets/d/1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4/edit?usp=sharing" 
    sheet = client.open(NOME_FILE).sheet1

    st.title("🏋️‍♂️ Maschera di Inserimento Sedi")

    # --- MASCHERA DI INSERIMENTO ---
    with st.container(border=True):
        st.subheader("📝 Registra Nuova Sessione")
        with st.form("workout_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                data = st.date_input("Data Allenamento")
                sede = st.selectbox("Sede", ["Sede 1", "Sede 2"])
            with c2:
                esercizio = st.text_input("Esercizio")
                carico = st.number_input("Carico (kg)", step=0.5)
            with c3:
                serie_rep = st.text_input("Serie x Rep (es. 4x12)")
                note = st.text_input("Note/Feedback")

            submit = st.form_submit_button("Salva nel Database Cloud")

            if submit:
                # Creiamo la riga
                nuova_riga = [str(data), sede, esercizio, carico, serie_rep, note]
                # Scrittura diretta sul foglio
                sheet.append_row(nuova_riga)
                st.success("✅ Dati inviati con successo!")
                st.balloons()

    # --- VISUALIZZAZIONE STORICO ---
    st.divider()
    st.subheader("📊 Storico Allenamenti Aggiornato")
    
    # Leggiamo i dati per mostrarli nell'app
    dati = sheet.get_all_records()
    if dati:
        df = pd.DataFrame(dati)
        # Mostra la tabella con l'ultima riga inserita in alto
        st.dataframe(df.iloc[::-1], use_container_width=True)
    
    if st.button("🔄 Forza Aggiornamento Tabella"):
        st.cache_data.clear()
        st.rerun()

except Exception as e:
    st.error("⚠️ Errore di connessione o permessi.")
    st.info("Assicurati di aver condiviso il foglio Google con l'email del Service Account e che il nome del file sia corretto.")
    if st.checkbox("Mostra dettagli errore"):
        st.write(e)
