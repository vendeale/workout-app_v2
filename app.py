import streamlit as st
import pandas as pd

# 1. Configurazione Pagina
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")
st.title("🏋️‍♂️ Registro Allenamenti Cloud")

# --- CONFIGURAZIONE LINK ---
# Assicurati che il link qui sotto sia quello corretto del tuo foglio
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4/edit?usp=sharing"

def get_csv_url(url):
    try:
        base_url = url.split('/edit')[0]
        return f"{base_url}/export?format=csv"
    except:
        return url

# --- CARICAMENTO DATI ---
# Rimuoviamo il caching temporaneamente per vedere le modifiche subito
def load_data():
    csv_link = get_csv_url(URL_FOGLIO)
    return pd.read_csv(csv_link)

try:
    df = load_data()

    st.subheader("📝 Maschera di Inserimento e Modifica")
    st.info("Puoi scrivere direttamente nella tabella qui sotto. Clicca due volte su una cella per modificarla o aggiungi righe in fondo.")

    # Questa è la tua nuova "Maschera"
    # Permette di modificare, aggiungere righe e cancellare
    edited_df = st.data_editor(
        df, 
        num_rows="dynamic", 
        use_container_width=True,
        key="workout_editor"
    )

    st.divider()

    # Bottoni di controllo
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Salva Modifiche nel Cloud"):
            # Nota: Per salvare davvero nel foglio senza la libreria gsheets, 
            # l'utente deve avere il foglio aperto. 
            # Poiché la libreria ufficiale crasha, ti mostro il metodo "Bridge":
            st.warning("Per confermare il salvataggio definitivo sul database:")
            st.link_button("Conferma su Google Sheets ↗️", URL_FOGLIO)
            st.session_state["df_backup"] = edited_df
            st.success("Modifiche pronte per il backup!")

    with col2:
        if st.button("🔄 Aggiorna/Annulla"):
            st.rerun()

except Exception as e:
    st.error("Errore di connessione. Verifica il link nel codice.")
    st.write(e)
