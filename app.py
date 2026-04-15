import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Workout Manager V3", page_icon="🚴‍♂️", layout="wide")

# --- FUNZIONI DI ACCESSO AI DATI (OTTIMIZZATE CON CACHE) ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)  # Cache per 10 minuti
def fetch_all_data(id_foglio):
    client = get_gspread_client()
    spreadsheet = client.open_by_key(id_foglio)
    sheet = spreadsheet.sheet1
    return sheet.get_all_records()

try:
    ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
    client = get_gspread_client()
    spreadsheet = client.open_by_key(ID_FOGLIO)
    sheet = spreadsheet.sheet1

    # Carichiamo i dati una volta sola per tutta l'esecuzione corrente
    dati_per_ricerca = fetch_all_data(ID_FOGLIO)

    # --- INTESTAZIONE ---
    col_l, col_logo, col_r = st.columns([2, 1, 2])
    with col_logo:
        try:
            st.image("logo.png", use_container_width=True)
        except:
            st.markdown("<h3 style='text-align: center; color: #ff4b4b;'>Richards Fitness</h3>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>Workout Manager</h1>", unsafe_allow_html=True)

    # --- SEZIONE: RICERCA RAPIDA ATLETA (USA LA CACHE) ---
    st.divider()
    with st.expander("🔍 **RICERCA RAPIDA ATLETA (Tutto l'archivio)**", expanded=False):
        c_search1, c_search2 = st.columns(2)
        with c_search1:
            search_nome = st.text_input("Filtra per Nome:", placeholder="Es. Mario")
        with c_search2:
            search_cognome = st.text_input("Filtra per Cognome:", placeholder="Es. Rossi")
        
        if (search_nome or search_cognome) and dati_per_ricerca:
            df_totale = pd.DataFrame(dati_per_ricerca)
            df_totale.columns = [str(c).strip() for c in df_totale.columns]
            
            mask = pd.Series([True] * len(df_totale))
            if search_nome:
                mask &= df_totale['Nome'].astype(str).str.contains(search_nome.strip(), case=False, na=False)
            if search_cognome:
                mask &= df_totale['Cognome'].astype(str).str.contains(search_cognome.strip(), case=False, na=False)
            
            risultati = df_totale[mask]
            if not risultati.empty:
                st.success(f"Trovate {len(risultati)} sessioni totali")
                colonne_target = ["Nome", "Cognome", "Data Pedalata", "Programma", "Livello", "Km totali", "Sede"]
                colonne_presenti = [c for c in colonne_target if c in df_totale.columns]
                st.dataframe(risultati[colonne_presenti].iloc[::-1], use_container_width=True)
            else:
                st.warning("Nessun risultato trovato.")

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
            
            with c5:
                lista_sessione = ["", "30 min", "45 min", "Altro..."]
                sess_sel = st.selectbox("Sessione *", options=lista_sessione)
                sess_extra = st.text_input("Se 'Altro', specifica durata:")
            
            with c6:
                lista_prog = ["", "Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."]
                prog_sel = st.selectbox("Programma *", options=lista_prog)
                prog_extra = st.text_input("Se 'Altro', specifica programma:")
            
            with c7:
                lista_livelli = ["", "1-resistenza", "2-resistenza", "3-resistenza", "1-variabile", "2-variabile", "3-variabile", "4-variabile", "5-variabile", "6-variabile", "Altro..."]
                liv_sel = st.selectbox("Livello *", options=lista_livelli)
                liv_extra = st.text_input("Se 'Altro', specifica livello:")

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
                sess_fin = sess_extra if sess_sel == "Altro..." else sess_sel
                liv_fin = liv_extra if liv_sel == "Altro..." else liv_sel
                
                if not nome or not cognome or not data_pedalata or not prog_fin or not sess_fin or not liv_fin or not sede:
                    st.error("⚠️ Compila i campi obbligatori!")
                else:
                    nome_completo = f"{nome} {cognome}".strip()
                    row = [
                        nome_completo, nome, cognome, 0, 
                        data_nascita.strftime("%d/%m/%Y") if data_nascita else "",
                        data_pedalata.strftime("%d/%m/%Y"), sess_fin, prog_fin, 
                        liv_fin, kmh, km, calorie, sede, 0, 0, 0
                    ]
                    sheet.append_row(row)
                    st.success("Dati salvati! Aggiornamento archivio...")
                    st.cache_data.clear() # Svuota la cache per forzare il ricaricamento al prossimo giro
                    st.rerun()

    # --- STORICO GLOBALE (ULTIMI 30 GIORNI) ---
    st.divider()
    st.subheader("📊 Ultime Sessioni Globali (Ultimi 30 giorni)")
    
    if dati_per_ricerca:
        df_globale = pd.DataFrame(dati_per_ricerca)
        df_globale.columns = [str(c).strip() for c in df_globale.columns]
        
        try:
            df_globale['Data_dt'] = pd.to_datetime(df_globale['Data Pedalata'], format='%d/%m/%Y', errors='coerce')
            un_mese_fa = datetime.now() - timedelta(days=30)
            df_filtrato = df_globale[df_globale['Data_dt'] >= un_mese_fa].copy()
            df_filtrato = df_filtrato.drop(columns=['Data_dt'])
            
            if not df_filtrato.empty:
                st.dataframe(df_filtrato.iloc[::-1], use_container_width=True)
            else:
                st.info("Nessuna sessione negli ultimi 30 giorni.")
        except:
            st.dataframe(df_globale.iloc[::-1], use_container_width=True)

        with st.expander("🗑️ Cancella inserimento errato"):
            opzioni = [{"label": f"{r.get('Nome', '')} {r.get('Cognome', '')} - {r.get('Data Pedalata', '')}", "idx": i+2} for i, r in enumerate(dati_per_ricerca)]
            if opzioni:
                sel = st.selectbox("Seleziona riga da eliminare:", opzioni, format_func=lambda x: x["label"])
                if st.button("Elimina definitivamente"):
                    sheet.delete_rows(sel["idx"])
                    st.cache_data.clear()
                    st.success("Riga eliminata!")
                    st.rerun()
    else:
        st.info("Nessun dato presente.")

except Exception as e:
    st.error("Errore critico.")
    st.exception(e)
