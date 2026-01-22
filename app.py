import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Inteligentní Spojovač", page_icon="🧩", layout="wide")

st.title("🧩 Sjednocení sloupců a doplnění dat")
st.markdown("""
Tato aplikace vezme data ze dvou souborů a **slije je do jedné tabulky pod stejné sloupce**.
1. Data ze **Sešitu1** mají přednost.
2. Pokud v Sešitu1 něco chybí (je prázdné), **doplní se to z Reportu**.
3. Pokud v Sešitu1 chybí celá delivery, **přidá se celá** na konec.
""")

# Funkce pro čištění textu a ID
def clean_id(val):
    return str(val).replace('.0', '').strip()

def load_data(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)

# Upload
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Hlavní (Sešit1)")
    file_sesit = st.file_uploader("Nahrajte Sešit1", type=['xlsx', 'csv'], key="f1")
with col2:
    st.subheader("2. Zdroj dat (Report)")
    file_report = st.file_uploader("Nahrajte Spojený report", type=['xlsx', 'csv'], key="f2")

if file_sesit and file_report:
    if st.button("Sjednotit a Doplnit"):
        with st.spinner('Sjednocuji sloupce a doplňuji data...'):
            try:
                # 1. Načtení
                df_main = load_data(file_sesit)
                df_new = load_data(file_report)

                # Čištění názvů sloupců (odstranění mezer na konci názvů, např. "Weight (kg)   ")
                df_main.columns = df_main.columns.str.strip()
                df_new.columns = df_new.columns.str.strip()

                # Klíčový sloupec
                key = 'DN NUMBER (SAP)'
                
                # Pokud se klíč v novém souboru jmenuje jinak, přejmenujeme ho
                if 'Zakázka (Delivery)' in df_new.columns:
                    df_new = df_new.rename(columns={'Zakázka (Delivery)': key})

                # Čištění ID (aby se to správně spárovalo)
                df_main[key] = df_main[key].apply(clean_id)
                df_new[key] = df_new[key].apply(clean_id)

                # 2. MAPOVÁNÍ SLOUPCŮ (Z češtiny do angličtiny podle Sešitu1)
                # Tím zajistíme, že data padnou do stejných sloupců
                column_mapping = {
                    'Materiál': 'Material',
                    'Počet kusů': 'Number of pieces',
                    'Počet palet': 'Number of pallets',
                    'Počet KLT': 'Number of KLTs',
                    'Počet plných KLT': 'Full KLTs',
                    'Počet prázdných KLT': 'Empty KLTs',
                    'Počet kartonů': 'Number of cartons',
                    'Váha (KG)': 'Weight (kg)',  # Pozor, v Sešitu1 to musí sedět přesně
                    'Detail Obalů': 'Comment'    # Například, nebo vytvoříme nový
                }
                
                # Přejmenování v novém reportu
                df_new = df_new.rename(columns=column_mapping)

                # 3. IDENTIFIKACE STAVU (Před spojením)
                main_ids = set(df_main[key])
                new_ids = set(df_new[key])
                
                # Určení statusu pro každý řádek
                def get_status(row_id):
                    if row_id in main_ids and row_id in new_ids:
                        return "Existuje (Doplněno)"
                    elif row_id in new_ids and row_id not in main_ids:
                        return "NOVÉ (Přidáno)"
                    else:
                        return "Pouze v Sešitu"

                # 4. SPOJENÍ (COMBINE FIRST)
                # Nastavíme ID jako index, aby pandas věděl, co k čemu patří
                df_main = df_main.set_index(key)
                df_new = df_new.set_index(key)

                # Samotné sloučení: df_main má přednost, díry se lepí z df_new
                df_final = df_main.combine_first(df_new)
                
                # Reset indexu, abychom měli DN NUMBER zase jako sloupec
                df_final = df_final.reset_index()

                # Přidání sloupce Status
                df_final.insert(0, 'Status_Analýzy', df_final[key].apply(get_status))

                # 5. KONTROLA CHYBĚJÍCÍCH HODNOT
                # Definujeme sloupce, které považujeme za povinné pro "kompletní delivery"
                critical_cols = ['Material', 'Number of pieces', 'Weight (kg)']
                
                # Funkce pro kontrolu
                def check_completeness(row):
                    missing = []
                    for col in critical_cols:
                        if col in row.index and (pd.isna(row[col]) or str(row[col]).strip() == ''):
                            missing.append(col)
                    if missing:
                        return f"⚠️ Chybí: {', '.join(missing)}"
                    return "OK"

                df_final.insert(1, 'Kontrola_Dat', df_final.apply(check_completeness, axis=1))

                # --- VÝSTUP ---
                st.success("Hotovo! Data jsou sjednocena ve stejných sloupcích.")
                
                # Statistiky
                st.write("### Statistiky")
                col_m1, col_m2 = st.columns(2)
                col_m1.metric("Celkový počet řádků", len(df_final))
                col_m2.metric("Nové (přidané) řádky", len(df_final[df_final['Status_Analýzy'] == 'NOVÉ (Přidáno)']))

                # Náhled problémových (nekompletních)
                incomplete = df_final[df_final['Kontrola_Dat'] != 'OK']
                if not incomplete.empty:
                    st.warning(f"Nalezeno {len(incomplete)} řádků s chybějícími daty.")
                    with st.expander("Zobrazit nekompletní řádky"):
                        st.dataframe(incomplete)
                
                # Náhled výsledku
                st.subheader("Náhled výsledné tabulky")
                st.dataframe(df_final.head(50))

                # Export
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Final_Data')
                    
                    # Formátování
                    workbook = writer.book
                    worksheet = writer.sheets['Final_Data']
                    
                    # Červená pro chybějící data
                    red_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                    green_format = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
                    
                    worksheet.conditional_format('B2:B99999', {'type': 'text', 'criteria': 'containing', 'value': 'Chybí', 'format': red_format})
                    worksheet.conditional_format('A2:A99999', {'type': 'text', 'criteria': 'containing', 'value': 'NOVÉ', 'format': green_format})

                output.seek(0)
                st.download_button(
                    label="📥 Stáhnout sjednocený soubor (.xlsx)",
                    data=output,
                    file_name="sjednoceny_report_final.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                st.error(f"Chyba při zpracování: {e}")
