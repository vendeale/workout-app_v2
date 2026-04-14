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

    st.title("🚴‍♂️ Workout Manager - Sedi Prati & Corso Trieste")

    # --- MASCHERA DI INSERIMENTO ---
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
                programma = st.text_input("Programma *")
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

            st.markdown("##### ❤️ Frequenza Cardiaca")
            c12, c13, c14, c15 = st.columns(4)
            with c12:
                fc_attuale = st.number_input("FC Attuale", min_value=0, step=1, value=0)
            with c13:
                fc_min = st.number_input("FC Minima", min_value=0, step=1, value=0)
            with c14:
                fc_max = st.number_input("FC Massima", min_value=0, step=1, value=0)
            with c15:
                fc_media = st.number_input("FC Media", min_value=0, step=1, value=0)

            st.write("* Campi obbligatori")
            submit = st.form_submit_button("🚀 Salva Sessione")

            if submit:
                # LISTA CONTROLLI MANDATORI
                mancanti = []
                if not nome: mancanti.append("Nome")
                if not cognome: mancanti.append("Cognome")
                if data_pedalata is None: mancanti.append("Data Pedalata")
                if not sessione: mancanti.append("Sessione")
                if not programma: mancanti.append("Programma")
                if not livello: mancanti.append("Livello")
                if kmh == 0.0: mancanti.append("Km/h")
                if km == 0.0: mancanti.append("Km totali")
                if calorie == 0: mancanti.append("Calorie")
                if not sede: mancanti.append("Sede")

                if mancanti:
                    st.error(f"⚠️ Errore! Compila i seguenti campi obbligatori: {', '.join(mancanti)}")
                else:
                    # AUTOMATISMO NOME & COGNOME
                    nome_completo_auto = f"{nome} {cognome}".strip()
                    
                    data_nascita_str = data_nascita.strftime("%d/%m/%Y") if data_nascita else ""
                    data_pedalata_str = data_pedalata.strftime("%d/%m/%Y")

                    # La Colonna A del tuo foglio riceve il valore generato automaticamente
                    nuova_riga = [
                        nome_completo_auto, # Colonna A (Nome&Cognome)
                        nome,               # Colonna B (Nome)
                        cognome,            # Colonna C (Cognome)
                        fc_attuale,         # Colonna D (FC Attuale)
                        data_nascita_str,   # Colonna E
                        data_pedalata_str,  # Colonna F
                        sessione,           # Colonna G
                        programma,          # Colonna H
                        livello,            # Colonna I
                        kmh,                # Colonna J
                        km,                 # Colonna K
                        calorie,            # Colonna L
                        sede,               # Colonna M
                        fc_min,             # Colonna N
                        fc_max,             # Colonna O
                        fc_media            # Colonna P
                    ]
                    
                    sheet.append_row(nuova_riga)
                    st.success(f"✅ Dati di {nome_completo_auto} salvati con successo!")
                    st.balloons()
                    st.cache_data.clear()

    # --- VISUALIZZAZIONE E CANCELLAZIONE ---
    st.divider()
    st.subheader("📊 Storico Sessioni")
    
    dati_raw = sheet.get_all_records()
    if dati_raw:
        df = pd.DataFrame(dati_raw)
        st.dataframe(df.iloc[::-1], use_container_width=True)

        st.divider()
        with st.expander("🗑️ Zona Pericolo: Cancella un inserimento errato"):
            st.warning("Attenzione: la cancellazione è definitiva.")
            opzioni_cancellazione = []
            for i, row in enumerate(dati_raw):
                # Usiamo il campo 'Nome&Cognome' del foglio per l'etichetta se disponibile
                identificativo = row.get('Nome&Cognome') if row.get('Nome&Cognome') else f"{row.get('Nome')} {row.get('Cognome')}"
                opzioni_cancellazione.append({
                    "label": f"Riga {i+2}: {identificativo} - {row.get('Data Pedalata')}",
                    "index": i + 2
                })
            
            selezione = st.selectbox("Seleziona la riga da eliminare", 
                                     options=opzioni_cancellazione, 
                                     format_func=lambda x: x["label"])
            
            conferma = st.checkbox("Confermo di voler eliminare questa riga")
            
            if st.button("Elimina Definitivamente"):
                if conferma:
                    sheet.delete_rows(selezione["index"])
                    st.success(f"Riga eliminata con successo!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Spunta la casella di conferma.")
    else:
        st.info("Nessun dato presente.")

except Exception as e:
    st.error("Errore di sistema.")
    st.code(e)
