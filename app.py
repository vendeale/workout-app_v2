import streamlit as st
import pandas as pd
import requests

# 1. Configurazione Pagina
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")
st.title("🏋️‍♂️ Registro Allenamenti Cloud")

# --- CONFIGURAZIONE ---
# Incolla qui il link del tuo foglio Google (quello con permesso Editor)
URL_FOGLIO = "IL_TUO_LINK_DI_GOOGLE_SHEETS"

# Funzione per trasformare il link in formato CSV per la lettura
def get_csv_url(url):
    return url.split("/edit")[0] + "/export?format=csv"

# --- LOGICA CARICAMENTO ---
@st.cache_data(ttl=5)
def load_data():
    return pd.read_csv(get_csv_url(URL_FOGLIO))

try:
    df = load_data()
    colonne = df.columns.tolist()

    tab1, tab2 = st.tabs(["➕ Nuovo Inserimento", "📊 Storico Cloud"])

    with tab1:
        st.subheader("Inserisci i dati")
        with st.form("form_input", clear_on_submit=True):
            nuovi_dati = {}
            cols = st.columns(3)
            for i, col_name in enumerate(colonne):
                with cols[i % 3]:
                    nuovi_dati[col_name] = st.text_input(f"{col_name}")
            
            submit = st.form_submit_button("Invia al Cloud")
            
            if submit:
                # Per scrivere senza la libreria gsheets, il modo più stabile
                # su Streamlit Cloud è usare un piccolo script o il metodo gspread.
                # Ma visto che la libreria non carica, ti mostro come farlo via Link.
                st.info("Per salvare: copia i dati nel foglio Google. L'app sincronizzerà tutto.")
                st.link_button("Apri Foglio per Modificare ↗️", URL_FOGLIO)

    with tab2:
        st.subheader("Dati Sincronizzati")
        st.dataframe(df.iloc[::-1], use_container_width=True)
        if st.button("🔄 Aggiorna Tabella"):
            st.cache_data.clear()
            st.rerun()

except Exception as e:
    st.error("Errore di caricamento. Verifica il link del foglio.")
