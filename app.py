import streamlit as st
import pandas as pd

# Configurazione Pagina
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")
st.title("🏋️‍♂️ Registro Allenamenti Cloud")

# Link del tuo foglio (quello che abbiamo visto funzionare)
URL_FOGLIO = "IL_TUO_LINK_DI_GOOGLE_SHEETS"

def get_csv_url(url):
    try:
        base_url = url.split('/edit')[0]
        return f"{base_url}/export?format=csv"
    except:
        return url

# Caricamento dati
try:
    csv_link = get_csv_url(URL_FOGLIO)
    df = pd.read_csv(csv_link)
    
    st.subheader("Storico Allenamenti")
    st.dataframe(df.iloc[::-1], use_container_width=True)
    
    st.divider()
    st.link_button("➕ Apri Foglio per Inserire Dati", URL_FOGLIO)
    
    if st.button("🔄 Aggiorna Tabella"):
        st.cache_data.clear()
        st.rerun()

except Exception as e:
    st.error("Errore di connessione. Verifica il link del foglio.")
