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
            st.markdown("<h3 style='text-align: center;'>Richards Fitness</h3>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- MASCHERA DI INSERIMENTO (Sempre in alto) ---
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
                    st.success("Salvataggio completato!")
                    st.cache_data.clear()

    # --- SEZIONE BASSA: STORICO E RICERCA (AFFIANCATI) ---
    st.divider()
    col_storia, col_ricerca = st.columns([1.2, 1]) # Bilanciamo lo spazio tra le due sezioni

    dati_raw = sheet.get_all_records()
    df_totale = pd.DataFrame(dati_raw) if dati_raw else pd.DataFrame()

    with col_storia:
        st.subheader("📊 Ultime Sessioni Globali")
        if not df_totale.empty:
            st.dataframe(df_totale.iloc[::-1].head(10), use_container_width=True)
            
            with st.expander("🗑️ Cancella inserimento errato"):
                opzioni = [{"label": f"{r['Nome']} {r['Cognome']} - {r['Data Pedalata']}", "idx": i+2} for i, r in enumerate(dati_raw)]
                sel = st.selectbox("Seleziona riga da eliminare:", opzioni, format_func=lambda x: x["label"])
                if st.button("Elimina definitivamente"):
                    sheet.delete_rows(sel["idx"])
                    st.cache_data.clear()
                    st.rerun()
        else:
            st.info("Nessun dato presente.")

    with col_ricerca:
        st.subheader("🔍 Cerca Storico Atleta")
        search_query = st.text_input("Inserisci nome o cognome:", placeholder="Es: Mario...")
        
        if search_query and not df_totale.empty:
            # Filtro intelligente su tutto il DataFrame
            mask = df_totale.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            risultati = df_totale[mask]
            
            if not risultati.empty:
                st.write(f"Storico per: **{search_query}**")
                colonne_mostra = ["Data Pedalata", "Programma", "Livello", "Km totali", "FC Media"]
                # Usiamo dataframe o table per i risultati della ricerca
                st.dataframe(risultati[colonne_mostra].iloc[::-1], use_container_width=True)
            else:
                st.warning("Nessun atleta trovato.")
        elif not search_query:
            st.info("Digita un nome per vedere il suo storico dedicato.")

except Exception as e:
    st.error("Errore di connessione al database.")
    st.code(e)
