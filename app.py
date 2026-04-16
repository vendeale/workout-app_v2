import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from fpdf import FPDF
import io
import os

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Aquatime Workout Manager", page_icon="🚴‍♂️", layout="wide")

@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def fetch_all_data(id_foglio):
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(id_foglio)
        sheet = spreadsheet.sheet1
        return sheet.get_all_records()
    except:
        return []

def get_col_name(columns, keywords, avoid=None):
    for col in columns:
        c_up = str(col).upper().strip()
        if any(key.upper() in c_up for key in keywords):
            if avoid and any(a.upper() in c_up for a in avoid): continue
            return col
    return None

# --- APP LOGIC ---
ID_FOGLIO = "1ngWM4rKWmcLDpOH79JDsRQ3QkGj5dkywQ7nTl91x1W4"
dati_raw = fetch_all_data(ID_FOGLIO)

# 1. LOGO
c_l, c_c, c_r = st.columns([1, 2, 1])
with c_c:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    else: st.title("AQUATIME")

# 2. RICERCA (Omettiamo per brevità la parte ricerca, resta uguale alla precedente)

# 3. NUOVA SESSIONE (Senza st.form per permettere l'apparizione dei box "Altro")
st.divider()
st.subheader("📝 Nuova Sessione")

with st.container(border=True):
    # Dati Anagrafici
    r1_1, r1_2, r1_3 = st.columns(3)
    nome = r1_1.text_input("Nome *")
    cognome = r1_2.text_input("Cognome *")
    sede = r1_3.selectbox("Sede *", ["Prati", "Corso Trieste"], index=None, placeholder="Scegli sede...")

    # Selezioni con Logica "Altro" (Appaiono subito perché fuori dal form rigido)
    st.write("---")
    c_data, c_sess, c_prog, c_liv = st.columns(4)
    
    data_s = c_data.date_input("Data *", value=None, format="DD/MM/YYYY")
    
    durata_sel = c_sess.selectbox("Sessione *", ["30 min", "45 min", "Altro..."], index=None, placeholder="Scegli...")
    final_durata = durata_sel
    if durata_sel == "Altro...":
        final_durata = c_sess.text_input("Specifica Sessione", placeholder="es. 60 min")
        
    prog_sel = c_prog.selectbox("Programma *", ["Forma", "Expert", "Sportivo", "Salute", "Manuale", "Altro..."], index=None, placeholder="Scegli...")
    final_prog = prog_sel
    if prog_sel == "Altro...":
        final_prog = c_prog.text_input("Specifica Programma", placeholder="es. HIIT")
        
    liv_sel = c_liv.selectbox("Livello *", ["1-res", "2-res", "3-res", "1-var", "2-var", "3-var", "Altro..."], index=None, placeholder="Scegli...")
    final_liv = liv_sel
    if liv_sel == "Altro...":
        final_liv = c_liv.text_input("Specifica Livello", placeholder="es. Pro")

    st.write("---")
    
    # Dati Tecnici
    r3_1, r3_2, r3_3 = st.columns(3)
    vel = r3_1.number_input("Km/h *", min_value=0.0, step=0.1)
    dist = r3_2.number_input("Km *", min_value=0.0, step=0.1)
    cal = r3_3.number_input("Calorie *", min_value=0)

    # Pulsante di salvataggio manuale
    if st.button("💾 Salva Sessione", type="primary", use_container_width=True):
        if nome and cognome and sede and data_s and final_durata and final_prog and final_liv:
            try:
                client = get_gspread_client()
                sheet = client.open_by_key(ID_FOGLIO).sheet1
                riga = [f"{nome} {cognome}", nome, cognome, 0, "", data_s.strftime("%d/%m/%Y"), 
                        final_durata, final_prog, final_liv, vel, dist, cal, sede, 0, 0, 0]
                sheet.append_row(riga)
                st.cache_data.clear()
                st.success(f"Sessione di {nome} salvata con successo!")
                st.rerun()
            except Exception as e:
                st.error(f"Errore durante il salvataggio: {e}")
        else:
            st.error("Per favore, compila tutti i campi obbligatori (*) prima di salvare.")

# 4. ARCHIVIO E CANCELLAZIONE (Resta uguale)
st.divider()
st.subheader("📊 Archivio Recente (30gg)")
if dati_raw:
    df_glob = pd.DataFrame(dati_raw)
    df_glob.columns = [str(c).strip() for c in df_glob.columns]
    c_data_g = get_col_name(df_glob.columns, ["DATA"], avoid=["NASCITA"])
    
    if c_data_g:
        df_glob[c_data_g] = pd.to_datetime(df_glob[c_data_g], dayfirst=True, errors='coerce')
        limite = datetime.now() - timedelta(days=30)
        df_recenti = df_glob[df_glob[c_data_g] >= limite].copy()
        
        if not df_recenti.empty:
            df_rec_view = df_recenti.sort_values(c_data_g, ascending=False)
            df_display = df_rec_view.copy()
            df_display[c_data_g] = df_display[c_data_g].dt.strftime('%d/%m/%Y')
            st.dataframe(df_display, use_container_width=True)

            with st.expander("🗑️ Cancella riga"):
                opzioni = [{"label": f"{r[c_data_g].strftime('%d/%m/%Y')} - {r['Nome']} {r['Cognome']}", "idx": i+2} 
                          for i, r in df_rec_view.iterrows()]
                scelta = st.selectbox("Quale riga vuoi eliminare?", opzioni, format_func=lambda x: x["label"], index=None, placeholder="Seleziona...")
                if st.button("Elimina definitivamente"):
                    if scelta:
                        client = get_gspread_client()
                        client.open_by_key(ID_FOGLIO).sheet1.delete_rows(scelta["idx"])
                        st.cache_data.clear()
                        st.rerun()
