import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Workout Manager V3", page_icon="🚴‍♂️", layout="wide")

@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

try:
    client = get_gspread_client()
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4" 
    spreadsheet = client.open_by_key(ID_FOGLIO)
    sheet = spreadsheet.sheet1 

    # --- INTESTAZIONE CON LOGO ---
    col_l, col_logo, col_r = st.columns([2, 1, 2])
    with col_logo:
        try:
            st.image("logo.png", use_container_width=True)
        except:
            st.markdown("<h3 style='text-align: center;'>Richards Fitness</h3>", unsafe_allow_html=True)

    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- SEZIONE: CHATBOT / RICERCA ATLETA ---
    st.divider()
    with st.expander("🔍 **RICERCA RAPIDA ATLETA (Chatbot Storico)**", expanded=False):
        st.write("Inserisci il nome o il cognome per vedere tutte le sessioni passate.")
        search_query = st.text_input("Cerca atleta:", placeholder="Es. Mario Rossi...")
        
        if search_query:
            dati_totali = sheet.get_all_records()
            if dati_totali:
                df_totale = pd.DataFrame(dati_totali)
                # Filtriamo per Nome&Cognome, Nome o Cognome (case insensitive)
                filtro = df_totale.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
                risultati = df_totale[filtro]
                
                if not risultati.empty:
                    st.success(f"Trovate {len(risultati)} sessioni per '{search_query}'")
                    colonne_vista = ["Data Pedalata", "Programma", "Livello", "Km totali", "Sede", "FC Media"]
                    st.table(risultati[colonne_vista].iloc[::-1]) 
                else:
                    st.warning("Nessun risultato trovato per questo nome.")

    # --- MASCHERA DI INSERIMENTO ---
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Registra Nuova Sessione")
        with st.form("workout_form", clear_on_submit=True):
            st.markdown("##### 👤 Atleta")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                nome = st.text_input("Nome *")
            with c2:
                cognome = st.text_input("Cognome *")
            with c3:
                data_nascita = st.date_input("Data di Nascita", value=None, min_value=datetime(1930, 1, 1), max_value=datetime.today(), format="DD/MM/YYYY")

            st.divider()
            st.markdown("##### 📅 Sessione e Programma")
            c4, c5, c6, c7 = st.columns(4)
            with c4:
                data_pedalata = st.date_input("Data Pedalata *", value=None, format="DD/MM/YYYY")
            with c5:
                sessione = st.text_input("Sessione *")
            with c6:
                lista_programmi = ["", "Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."]
                programma_scelto = st.selectbox("Programma *", options=lista_programmi)
                programma_extra = st.text_input("Se 'Altro', specifica:")
            with c7:
                livello = st.text_input("Livello *")

            st.divider()
            st.markdown("##### 📈 Performance")
            c8, c9, c10, c11 = st.columns(4)
            with c8:
                kmh = st.number_input("Km/h *", min_value=0.0, step=0.1, value=0.0)
            with c9:
                km = st.number_input("Km totali *", min_value=0.0, step=0.1, value=0.0)
            with c10:
                calorie = st.number_input("Calorie *", min_value=0, step=1, value=0)
            with c11:
                sede = st.selectbox("Sede *", ["", "Prati", "Corso Trieste"])

            st.markdown("##### ❤️ Frequenza Cardiaca (Opzionali)")
            c12, c13, c14, c15 = st.columns(4)
            with c12: fc_attuale = st.number_input("FC Attuale", value=0)
            with c13: fc_min = st.number_input("FC Minima", value=0)
            with c14: fc_max = st.number_input("FC Massima", value=0)
            with c15: fc_media = st.number_input("FC Media", value=0)

            submit = st.form_submit_button("🚀 Salva Sessione")

            if submit:
                prog_fin = programma_extra if programma_scelto == "Altro..." else programma_scelto
                mancanti = []
                if not nome: mancanti.append("Nome")
                if not cognome: mancanti.append("Cognome")
                if not data_pedalata: mancanti.append("Data Pedalata")
                if not prog_fin: mancanti.append("Programma")
                if not sede: mancanti.append("Sede")
                
                if mancanti:
                    st.error(f"⚠️ Mancano: {', '.join(mancanti)}")
                else:
                    nome_completo = f"{nome} {cognome}".strip()
                    row = [
                        nome_completo, nome, cognome, fc_attuale, 
                        data_nascita.strftime("%d/%m/%Y") if data_nascita else "",
                        data_pedalata.strftime("%d/%m/%Y"), sessione, prog_fin, 
                        livello, kmh, km, calorie, sede, fc_min, fc_max, fc_media
                    ]
                    sheet.append_row(row)
                    st.success("Salvataggio completato!")
                    st.cache_data.clear()

    # --- STORICO GENERALE E CANCELLAZIONE ---
    st.divider()
    st.subheader("📊 Ultime Sessioni Globali")
    dati_raw = sheet.get_all_records()
    if dati_raw:
        df = pd.DataFrame(dati_raw)
        st.dataframe(df.iloc[::-1].head(10), use_container_width=True)

        with st.expander("🗑️ Cancella inserimento errato"):
            opzioni = [{"label": f"{r['Nome']} {r['Cognome']} - {r['Data Pedalata']}", "idx": i+2} for i, r in enumerate(dati_raw)]
            sel = st.selectbox("Seleziona riga:", opzioni, format_func=lambda x: x["label"])
            if st.button("Conferma Eliminazione"):
                sheet.delete_rows(sel["idx"])
                st.cache_data.clear()
                st.rerun()

except Exception as e:
    st.error("Errore di connessione.")
    st.code(e)
