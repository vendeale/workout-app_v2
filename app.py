import streamlit as st
import pandas as pd

# 1. Configurazione Pagina
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")

st.title("🏋️‍♂️ Workout Manager Cloud")

# --- CONFIGURAZIONE LINK ---
# Incolla qui il link del tuo foglio Google (Condiviso: Chiunque abbia il link può visualizzare)
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4/edit?usp=sharing"

# Incolla qui il link del tuo Google Form
URL_FORM = "https://docs.google.com/spreadsheets/d/1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4/edit?pli=1&gid=1160386155#gid=1160386155"

def get_csv_url(url):
    try:
        base_url = url.split('/edit')[0]
        return f"{base_url}/export?format=csv"
    except:
        return url

# --- INTERFACCIA ---
tab1, tab2 = st.tabs(["📝 Inserisci Allenamento", "📊 Storico Dati"])

with tab1:
    st.subheader("Nuova Sessione")
    st.info("Compila i campi qui sotto per salvare l'allenamento nel database cloud.")
    
    # Inseriamo il Google Form come maschera d'inserimento
    st.components.v1.iframe(URL_FORM, height=800, scrolling=True)

with tab2:
    st.subheader("Dati Sincronizzati")
    try:
        csv_link = get_csv_url(URL_FOGLIO)
        # Leggiamo i dati (usiamo un trucco per forzare l'aggiornamento)
        df = pd.read_csv(csv_link)
        
        # Mostra la tabella (i più recenti in alto)
        st.dataframe(df.iloc[::-1], use_container_width=True)
        
        if st.button("🔄 Aggiorna Tabella"):
            st.cache_data.clear()
            st.rerun()
            
    except Exception as e:
        st.error("In attesa dei dati... Assicurati che il link del foglio sia corretto.")
