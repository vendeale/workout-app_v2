import streamlit as st
import pandas as pd

# 1. Configurazione Pagina
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")
st.title("🏋️‍♂️ Registro Allenamenti Cloud")

# --- CONFIGURAZIONE LINK ---
# Sostituisci questo link con quello del tuo foglio Google.
# IMPORTANTE: Il foglio deve essere condiviso come "Chiunque abbia il link può visualizzare"
URL_FOGLIO = "INSERISCI_QUI_IL_TUO_LINK_DI_GOOGLE_SHEETS"

# Trasformazione del link per la lettura CSV diretta
def get_csv_url(url):
    try:
        if "/edit" in url:
            return url.split("/edit")[0] + "/export?format=csv"
        return url
    except:
        return url

csv_url = get_csv_url(URL_FOGLIO)

# --- FUNZIONE CARICAMENTO ---
@st.cache_data(ttl=10) # Aggiorna i dati ogni 10 secondi
def load_data(url):
    return pd.read_csv(url)

try:
    # Caricamento dati
    df = load_data(csv_url)

    # Interfaccia
    tab1, tab2 = st.tabs(["📊 Visualizza Dati", "📝 Come inserire"])

    with tab1:
        st.subheader("Dati in tempo reale dal Cloud")
        st.dataframe(df, use_container_width=True)
        
        if st.button("🔄 Forza Aggiornamento"):
            st.cache_data.clear()
            st.rerun()

    with tab2:
        st.info("💡 **Nota per le Sedi:**")
        st.write("""
        Per garantire la massima stabilità, l'inserimento dati va fatto direttamente 
        sul Foglio Google condiviso. L'app sincronizzerà i cambiamenti istantaneamente.
        """)
        st.link_button("Vai al Foglio Google ↗️", URL_FOGLIO)

except Exception as e:
    st.error("Errore di connessione al Foglio Google.")
    st.info("Assicurati che il link nel codice sia corretto e che il foglio sia condiviso con 'Chiunque abbia il link'.")
    st.exception(e)
