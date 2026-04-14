import streamlit as st
import pandas as pd

# --- FIX IMPORTAZIONE ---
try:
    from streamlit_gsheetsconnection import GSheetsConnection
except ImportError:
    try:
        from st_gsheets_connection import GSheetsConnection
    except ImportError:
        st.error("Libreria di connessione non trovata. Per favore contatta l'assistenza.")
        st.stop()

# Configurazione Pagina
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")
st.title("🏋️‍♂️ Registro Allenamenti Cloud")

# Connessione
conn = st.connection("gsheets", type=GSheetsConnection)

# Caricamento dati
df = conn.read(ttl=0)
colonne = df.columns.tolist()

tab1, tab2 = st.tabs(["➕ Nuovo Inserimento", "📊 Storico"])

with tab1:
    st.subheader("Inserisci Allenamento")
    with st.form("workout_form", clear_on_submit=True):
        nuovi_dati = {}
        cols = st.columns(3)
        for i, col in enumerate(colonne):
            with cols[i % 3]:
                nuovi_dati[col] = st.text_input(f"{col}")
        
        if st.form_submit_button("Invia al Foglio"):
            if any(nuovi_dati.values()):
                # Crea nuova riga e aggiorna
                nuova_riga = pd.DataFrame([nuovi_dati])
                df_aggiornato = pd.concat([df, nuova_riga], ignore_index=True)
                conn.update(data=df_aggiornato)
                st.success("✅ Dati salvati!")
                st.rerun()
            else:
                st.warning("Inserisci almeno un dato.")

with tab2:
    st.subheader("Dati nel Cloud")
    st.dataframe(df, use_container_width=True)
