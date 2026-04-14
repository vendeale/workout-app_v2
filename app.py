import streamlit as st
import pandas as pd

# 1. Configurazione Pagina
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")
st.title("🏋️‍♂️ Registro Allenamenti Cloud")

# --- CONFIGURAZIONE LINK ---
# Incolla qui il link che ottieni dal tasto "Condividi" di Google Sheets
URL_FOGLIO = "IL_TUO_LINK_DI_GOOGLE_SHEETS_QUI"

def get_csv_url(url):
    """Trasforma il link di condivisione in un link di esportazione CSV"""
    try:
        # Prende la parte del link prima di /edit e aggiunge l'esportazione csv
        base_url = url.split('/edit')[0]
        return f"{base_url}/export?format=csv"
    except Exception:
        return url

# --- LOGICA CARICAMENTO ---
@st.cache_data(ttl=5) # Aggiorna ogni 5 secondi
def load_data():
    csv_link = get_csv_url(URL_FOGLIO)
    # pandas legge direttamente il foglio come un file CSV
    return pd.read_csv(csv_link)

try:
    df = load_data()
    
    # Interfaccia a Tab
    tab1, tab2 = st.tabs(["📊 Visualizza Dati", "⚙️ Gestione"])

    with tab1:
        st.subheader("Tabella Allenamenti Aggiornata")
        # Mostriamo i dati (l'ultima riga in alto)
        st.dataframe(df.iloc[::-1], use_container_width=True)
        
        if st.button("🔄 Aggiorna Ora"):
            st.cache_data.clear()
            st.rerun()

    with tab2:
        st.info("🔓 **Accesso Editor Attivo**")
        st.write("Dato che hai i permessi di modifica, clicca il tasto sotto per aggiungere o cambiare i dati:")
        st.link_button("Apri Foglio Google per Inserire Dati ↗️", URL_FOGLIO)

except Exception as e:
    st.error("⚠️ Errore di connessione al foglio.")
    st.info("Controlla che il link sia corretto e che il foglio sia condiviso con 'Chiunque abbia il link'.")
    # Questo serve a noi per capire il problema tecnico se persiste
    if st.checkbox("Mostra dettagli errore"):
        st.write(e)
