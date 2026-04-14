import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")

# --- CONNESSIONE GOOGLE SHEETS ---
@st.cache_resource
def get_gspread_client():
    # Autorizzazioni necessarie per Sheets e Drive
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # Carica le credenziali dai Secrets di Streamlit
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], 
        scopes=scope
    )
    return gspread.authorize(creds)

try:
    client = get_gspread_client()
    
    # ID univoco del tuo foglio Google
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4" 
    spreadsheet = client.open_by_key(ID_FOGLIO)
    sheet = spreadsheet.sheet1 # Prende il primo tab del foglio

    st.title("🏋️‍♂️ Registro Allenamenti Sedi")

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
                carico = st.number_input("Carico (kg)", step=0.5, min_value=0.0)
            with c3:
                serie_rep = st.text_input("Serie x Rep (es. 4x12)")
                note = st.text_input("Note/Feedback")

            submit = st.form_submit_button("Salva nel Database Cloud")

            if submit:
                # Creiamo la riga da inviare al foglio
                nuova_riga = [str(data), sede, esercizio, carico, serie_rep, note]
                # Scrittura sul foglio
                sheet.append_row(nuova_riga)
                st.success("✅ Dati inviati con successo!")
                st.balloons()
                # Puliamo la cache per forzare il refresh dello storico
                st.cache_data.clear()

    # --- VISUALIZZAZIONE STORICO ---
    st.divider()
    st.subheader("📊 Storico Allenamenti Aggiornato")
    
    # Recupero dati dal foglio
    dati = sheet.get_all_records()
    if dati:
        df = pd.DataFrame(dati)
        # Mostra la tabella con l'ultima riga inserita in alto
        st.dataframe(df.iloc[::-1], use_container_width=True)
    else:
        st.info("Il database è attualmente vuoto. Inserisci il primo allenamento sopra!")
    
    if st.button("🔄 Aggiorna Tabella"):
        st.cache_data.clear()
        st.rerun()

except Exception as e:
    st.error("⚠️ Errore di connessione o permessi.")
    st.info("Verifica di aver condiviso il foglio con l'email del Service Account (Editor).")
    if st.checkbox("Mostra dettagli errore per assistenza"):
        st.code(e)
