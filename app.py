import streamlit as st
import pandas as pd
from st_gsheets_connection import GSheetsConnection

# 1. Configurazione Interfaccia
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")
st.title("🏋️‍♂️ Registro Allenamenti Cloud")

# 2. Connessione a Google Sheets
# Il link del foglio andrà messo nei "Secrets" di Streamlit, non qui!
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. Funzione per leggere i dati
def load_data():
    return conn.read(ttl=0)

try:
    df = load_data()
    colonne = df.columns.tolist()

    # Creazione Tab
    tab1, tab2 = st.tabs(["➕ Nuovo Inserimento", "📊 Visualizza Storico"])

    with tab1:
        st.subheader("Inserisci i dati dell'allenamento")
        with st.form("form_allenamento", clear_on_submit=True):
            nuovi_dati = {}
            # Crea automaticamente un campo per ogni colonna del tuo foglio
            cols = st.columns(3)
            for i, col_name in enumerate(colonne):
                with cols[i % 3]:
                    nuovi_dati[col_name] = st.text_input(f"{col_name}")
            
            if st.form_submit_button("Invia al Foglio Google"):
                new_row = pd.DataFrame([nuovi_dati])
                updated_df = pd.concat([df, new_row], ignore_index=True)
                conn.update(data=updated_df)
                st.success("✅ Dati salvati con successo!")
                st.rerun()

    with tab2:
        st.subheader("Dati attuali nel Cloud")
        st.dataframe(df, use_container_width=True)
        if st.button("🔄 Aggiorna Tabella"):
            st.rerun()

except Exception as e:
    st.warning("⚠️ In attesa di configurazione...")
    st.info("Configura il link del foglio Google nei 'Secrets' di Streamlit Cloud per iniziare.")
