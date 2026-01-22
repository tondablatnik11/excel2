import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Inteligentní Spojovač (Fix)", page_icon="🛡️", layout="wide")

st.title("🛡️ Sjednocení sloupců (Robustní verze)")
st.markdown("""
**Tato verze obsahuje opravy chyb:**
- Odstraňuje duplicitní sloupce.
- Řeší problémy s číselnými formáty.
- Bezpečně spojuje data.
""")

def clean_id_column(df, col_name):
    """Bezpečně převede sloupec na text a ošetří chyby i v případě duplicit."""
    if col_name in df.columns:
        data = df[col_name]
        # Pokud je sloupec duplicitní (vrací DataFrame), vezmeme jen první výskyt
        if isinstance(data, pd.DataFrame):
            data = data.iloc[:, 0]
        # Převedeme na string, odstraníme .0, ořežeme
        return data.astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    return None

def load_data(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file, low_memory=False)
    else:
        return pd.read_excel(uploaded_file)

# Upload sekce
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Hlavní (Sešit1)")
    file_sesit = st.file_uploader("Nahrajte Sešit1", type=['xlsx', 'csv'], key="f1")
with col2:
    st.subheader("2. Zdroj dat (Report)")
    file_report = st.file_uploader("Nahrajte Spojený report", type=['xlsx', 'csv'], key="f2")

if file_sesit and file_report:
    if st.button("Sjednotit a Doplnit"):
        with st.spinner('Čistím a spojuji data...'):
            try:
                # 1. Načtení dat
                df_main = load_data(file_sesit)
                df_new = load_data(file_report)

                # --- OPRAVA CHYB (Fix duplicate columns & types) ---
                # Odstranění duplicitních sloupců (necháme si jen první výskyt)
                df_main = df_main.loc[:, ~df_main.columns.duplicated()]
                df_new = df_new.loc[:, ~df_new.columns.duplicated()]

                # Převedení názvů sloupců na string (pro jistotu, kdyby tam byla čísla)
                df_main.columns = df_main.columns.astype(str).str.strip()
                df_new.columns = df_new.columns.astype(str).str.strip()
                # ---------------------------------------------------

                # Klíčový sloupec
                key = 'DN NUMBER (SAP)'
                
                # Pokud se klíč v novém souboru jmenuje 'Zakázka (Delivery)', přejmenujeme ho
                if 'Zakázka (Delivery)' in df_new.columns:
                    df_new = df_new.rename(columns={'Zakázka (Delivery)': key})

                # Kontrola existence klíče
                if key not in df_main.columns or key not in df_new.columns:
                    st.error(f"Chyba: Sloupec '{key}' nebyl nalezen. Zkontrolujte názvy sloupců.")
                    st.stop()

                # 2. ČIŠTĚNÍ ID (s novou bezpečnou funkcí)
                df_main[key] = clean_id_column(df_main, key)
                df_new[key] = clean_id_column(df_new, key)

                # 3. MAPOVÁNÍ SLOUPCŮ
                column_mapping = {
                    'Materiál': 'Material',
                    'Počet kusů': 'Number of pieces',
                    'Počet palet': 'Number of pallets',
                    'Počet KLT': 'Number of KLTs',
                    'Počet plných KLT': 'Full KLTs',
                    'Počet prázdných KLT': 'Empty KLTs',
                    'Počet kartonů': 'Number of cartons',
                    'Váha (KG)': 'Weight (kg)',
                    'Detail Obalů': 'Comment'
                }
                df_new = df_new.rename(columns=column_mapping)
                
                # Znovu odstraníme duplicity, kdyby rename vytvořil kolizi (např. Material už existoval)
                df_new = df_new.loc[:, ~df_new.columns.duplicated()]

                # 4. SPOJENÍ DAT (Merge)
                # Použijeme Outer Join
                merged = pd.merge(
                    df_main,
                    df_new,
                    on=key,
                    how='outer',
                    suffixes=('', '_new'), 
                    indicator=True
                )

                # 5. DOPLNĚNÍ CHYBĚJÍCÍCH HODNOT
                # Kde je v hlavním souboru prázdno, vezmeme data z _new
                for col in merged.columns:
                    if col.endswith('_new'):
                        original_col = col[:-4] # název bez _new
                        if original_col in merged.columns:
                            # fillna: doplní prázdná místa (NaN)
                            merged[original_col] = merged[original_col].fillna(merged[col])

                # Určení statusu
                def get_status(merge_ind):
                    if merge_ind == 'both': return "Existuje (Doplněno)"
                    if merge_ind == 'right_only': return "NOVÉ (Přidáno)"
                    return "Pouze v Sešitu"

                merged['Status_Analýzy'] = merged['_merge'].apply(get_status)

                # Úklid sloupců
                final_cols = [c for c in merged.columns if not c.endswith('_new') and c != '_merge']
                # Seřadíme: Status, Key, a zbytek
                cols_order = ['Status_Analýzy', key] + [c for c in final_cols if c not in ['Status_Analýzy', key]]
                df_final = merged[cols_order]

                # 6. KONTROLA KOMPLETNOSTI
                critical_cols = ['Material', 'Number of pieces', 'Weight (kg)']
                
                def check_completeness(row):
                    missing = []
                    for col in critical_cols:
                        val = row.get(col)
                        # Kontrola prázdnoty (NaN, None, prázdný string)
                        if pd.isna(val) or str(val).strip() == '' or str(val).lower() == 'nan':
                            missing.append(col)
                    if missing:
                        return f"⚠️ Chybí: {', '.join(missing)}"
                    return "OK"

                df_final.insert(1, 'Kontrola_Dat', df_final.apply(check_completeness, axis=1))

                # --- VÝSTUP ---
                st.success("Hotovo! Data byla úspěšně zpracována.")
                
                # Metriky
                n_new = len(df_final[df_final['Status_Analýzy'] == 'NOVÉ (Přidáno)'])
                n_inc = len(df_final[df_final['Kontrola_Dat'] != 'OK'])
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Celkem řádků", len(df_final))
                m2.metric("Nově přidáno", n_new)
                m3.metric("Nekompletní", n_inc, delta_color="inverse")

                # Náhled
                st.dataframe(df_final.head(50))

                # Export
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Final_Data')
                    
                    workbook = writer.book
                    worksheet = writer.sheets['Final_Data']
                    
                    red_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                    green_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
                    
                    # Podmíněné formátování
                    worksheet.conditional_format('B2:B5000', {'type': 'text', 'criteria': 'containing', 'value': 'Chybí', 'format': red_fmt})
                    worksheet.conditional_format('A2:A5000', {'type': 'text', 'criteria': 'containing', 'value': 'NOVÉ', 'format': green_fmt})

                output.seek(0)
                st.download_button("📥 Stáhnout výsledek (.xlsx)", output, "vysledek_analyzy.xlsx")

            except Exception as e:
                st.error(f"Chyba: {e}")
                st.write("Detail chyby pro debug:", str(e))
