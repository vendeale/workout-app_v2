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

    # --- INTESTAZIONE ---
    col_l, col_logo, col_r = st.columns([2, 1, 2])
    with col_logo:
        try:
            st.image("logo.png", use_container_width=True)
        except:
            st.markdown("<h3 style='text-align: center; color: #ff4b4b;'>Richards Fitness</h3>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- SEZIONE: RICERCA ATLETA ---
    st.divider()
    with st.expander("🔍 **RICERCA RAPIDA ATLETA**", expanded=False):
        search_query = st.text_input("Inserisci il Nome o il Cognome dell'atleta:", placeholder="Es. Ciocchetta...")
        
        if search_query:
            dati_totali = sheet.get_all_records()
            if dati_totali:
                df_totale = pd.DataFrame(dati_totali)
                df_totale.columns = [str(c).strip() for c in df_totale.columns]
                
                mask = (
                    df_totale['Nome'].astype(str).str.contains(search_query, case=False, na=False) | 
                    df_totale['Cognome'].astype(str).str.contains(search_query, case=False, na=False)
                )
                risultati = df_totale[mask]
                
                if not risultati.empty:
                    st.success(f"Trovate {len(risultati)} sessioni per '{search_query}'")
                    colonne_target = ["Data Pedalata", "Programma", "Livello", "Km totali", "Sede", "FC Media"]
                    colonne_presenti = [c for c in colonne_target if c in df_totale.columns]
                    st.dataframe(risultati[colonne_presenti].iloc[::-1], use_container_width=True)
                else:
                    st.warning(f"Nessun atleta trovato con il nome '{search_query}'")

    # --- MASCHERA DI INSERIMENTO ---
    st.divider()
    with st.container(border=True):
        st.subheader("📝 Registra Nuova Sessione")
        with st.form("workout_form", clear_on_submit=True):
            st.markdown("##### 👤 Atleta")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1: nome = st.text_input("Nome *")
            with c2: cognome = st.text_input("Cognome *")
            with c3: data_nascita = st.date_input("Data di Nascita", value=None, format="DD/MM/YYYY")

            st.divider()
            st.markdown("##### 📅 Sessione e Programma")
            c4, c5, c6, c7 = st.columns(4)
            with c4: data_pedalata = st.date_input("Data Pedalata *", value=None, format="DD/MM/YYYY")
            with c5: sessione = st.text_input("Sessione *")
            with c6:
                lista_prog = ["", "Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."]
                prog_sel = st.selectbox("Programma *", options=lista_prog)
                prog_extra = st.text_input("Se 'Altro', specifica:")
            with c7: livello = st.text_input("Livello *")

            st.divider()
            st.markdown("##### 📈 Performance")
            c8, c9, c10, c11 = st.columns(4)
            with c8: kmh = st.number_input("Km/h *", min_value=0.0, step=0.1)
            with c9: km = st.number_input("Km totali *", min_value=0.0, step=0.1)
            with c10: calorie = st.number_input("Calorie *", min_value=0)
            with c11: sede = st.selectbox("Sede *", ["", "Prati", "Corso Trieste"])

            submit = st.form_submit_button("🚀 Salva Sessione")

            if submit:
                prog_fin = prog_extra if prog_sel == "Altro..." else prog_sel
                if not nome or not cognome or not data_pedalata or not prog_fin or not sede:
                    st.error("⚠️ Compila tutti i campi obbligatori!")
                else:
                    nome_completo = f"{nome} {cognome}".strip()
                    row = [
                        nome_completo, nome, cognome, 0, 
                        data_nascita.strftime("%d/%m/%Y") if data_nascita else "",
                        data_pedalata.strftime("%d/%m/%Y"), sessione, prog_fin, 
                        livello, kmh, km, calorie, sede, 0, 0, 0
                    ]
                    sheet.append_row(row)
                    st.success("Dati salvati con successo!")
                    st.cache_data.clear()

    # --- STORICO GLOBALE (ELENCO COMPLETO) ---
    st.divider()
    st.subheader("📊 Ultime Sessioni Globali")
    dati_raw = sheet.get_all_records()
    if dati_raw:
        df_globale = pd.DataFrame(dati_raw)
        # Rimosso .head(10) per mostrare TUTTO lo storico
        st.dataframe(df_globale.iloc[::-1], use_container_width=True)

        with st.expander("🗑️ Cancella inserimento errato"):
            opzioni = [{"label": f"{r.get('Nome', '')} {r.get('Cognome', '')} - {r.get('Data Pedalata', '')}", "idx": i+2} for i, r in enumerate(dati_raw)]
            sel = st.selectbox("Seleziona riga da eliminare:", opzioni, format_func=lambda x: x["label"])
            if st.button("Elimina definitivamente"):
                sheet.delete_rows(sel["idx"])
                st.cache_data.clear()
                st.rerun()
    else:
        st.info("Nessun dato presente nel database.")

except Exception as e:
    st.error("Si è verificato un errore critico.")
    st.exception(e)
