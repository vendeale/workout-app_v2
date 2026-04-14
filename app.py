import streamlit as st
import pandas as pd

# --- LOGICA DI IMPORTAZIONE DINAMICA ---
# Questo risolve l'errore ModuleNotFoundError provando i due nomi registrati della libreria
try:
    from streamlit_gsheetsconnection import GSheetsConnection
except ImportError:
    try:
        from st_gsheets_connection import GSheetsConnection
    except ImportError:
        st.error("Errore: Libreria 'st-gsheets-connection' non trovata. Verifica il file requirements.txt")
        st.stop()

# 1. Configurazione della pagina
st.set_page_config(page_title="Workout Manager V2", page_icon="🏋️‍♂️", layout="wide")
st.title("🏋️‍♂️ Registro Allenamenti Cloud")

# 2. Connessione a Google Sheets
# Nota: La connessione cercherà le credenziali nei 'Secrets' di Streamlit Cloud
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Errore di connessione. Verifica di aver inserito il link del foglio nei Secrets.")
    st.stop()

# --- FUNZIONE PER CARICARE I DATI ---
@st.cache_data(ttl=0) # ttl=0 forza l'aggiornamento ad ogni refresh
def load_data():
    return conn.read()

# Caricamento dati
try:
    df = load_data()
    colonne = df.columns.tolist()
except Exception as e:
    st.warning("⚠️ Impossibile leggere il foglio. Verifica che sia 'Pubblicato sul Web' o che il link nei Secrets sia corretto.")
    st.stop()

# --- INTERFACCIA A TAB ---
tab1, tab2 = st.tabs(["➕ Nuovo Inserimento", "📊 Storico Allenamenti"])

with tab1:
    st.subheader("Inserisci i dettagli della sessione")
    with st.form("form_allenamento", clear_on_submit=True):
        nuovi_dati = {}
        
        # Distribuiamo i campi di input in 3 colonne per un look pulito
        cols = st.columns(3)
        for i, col_name in enumerate(colonne):
            with cols[i % 3]:
                if "data" in col_name.lower():
                    data_input = st.date_input(f"{col_name}", format="DD/MM/YYYY")
                    nuovi_dati[col_name] = data_input.strftime("%d/%m/%Y")
                else:
                    nuovi_dati[col_name] = st.text_input(f"{col_name}")
        
        if st.form_submit_button("Salva nel Cloud"):
            # Crea la nuova riga
            new_row = pd.DataFrame([nuovi_dati])
            # Uniscila ai dati esistenti
            updated_df = pd.concat([df, new_row], ignore_index=True)
            
            # Aggiorna il foglio Google
            conn.update(data=updated_df)
            st.success("✅ Dati salvati correttamente!")
            st.cache_data.clear() # Pulisce la memoria per mostrare i nuovi dati
            st.rerun()

with tab2:
    st.subheader("Dati in tempo reale dal Cloud")
    # Mostra la tabella ordinata per l'ultima riga inserita (la più recente in alto)
    st.dataframe(df.iloc[::-1], use_container_width=True)
    
    if st.button("🔄 Aggiorna Tabella"):
        st.cache_data.clear()
        st.rerun()
