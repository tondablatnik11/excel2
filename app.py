import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Inteligentní Spojovač (Oprava)", page_icon="🔧", layout="wide")

st.title("🔧 Sjednocení sloupců a doplnění dat")
st.markdown("""
**Opravená verze:** Tato aplikace bezpečněji spojí data i v případě duplicitních zakázek nebo různých formátů.
1. Data ze **Sešitu1** mají přednost.
2. Prázdná místa se doplní z **Reportu**.
3. Nové zakázky se přidají na konec.
""")

def clean_id_column(df, col_name):
    """Bezpečně převede sloupec na text a ošetří chyby."""
    if col_name in df.columns:
        # Převedeme na string, odstraníme .0, ořežeme mezery a nahradíme 'nan' za prázdné
        return df[col_name].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    return None

def load_data(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        # Low memory=False pomáhá s mixovanými typy dat při načítání
        return pd.read_csv(uploaded_file, low_memory=False)
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
        with st.spinner('Analyzuji a spojuji data...'):
            try:
                # 1. Načtení dat
                df_main = load_data(file_sesit)
                df_new = load_data(file_report)

                # Čištění názvů sloupců
                df_main.columns = df_main.columns.str.strip()
                df_new.columns = df_new.columns.str.strip()

                # Klíčový sloupec
                key = 'DN NUMBER (SAP)'
                
                # Pokud se klíč v novém souboru jmenuje 'Zakázka (Delivery)', přejmenujeme ho
                if 'Zakázka (Delivery)' in df_new.columns:
                    df_new = df_new.rename(columns={'Zakázka (Delivery)': key})

                # Kontrola existence klíče
                if key not in df_main.columns or key not in df_new.columns:
                    st.error(f"Chyba: Sloupec '{key}' nebyl nalezen v jednom ze souborů.")
                    st.stop()

                # 2. PŘEVOD KLÍČŮ NA TEXT (Prevence chyby 'Conversion failed')
                df_main[key] = clean_id_column(df_main, key)
                df_new[key] = clean_id_column(df_new, key)

                # 3. MAPOVÁNÍ SLOUPCŮ (Z češtiny do angličtiny)
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

                # 4. IDENTIFIKACE STAVU
                main_ids = set(df_main[key])
                new_ids = set(df_new[key])
                
                def get_status(row_id, merge_indicator):
                    if merge_indicator == 'both':
                        return "Existuje (Doplněno)"
                    elif merge_indicator == 'right_only':
                        return "NOVÉ (Přidáno)"
                    else:
                        return "Pouze v Sešitu"

                # 5. BEZPEČNÉ SPOJENÍ (Merge místo Combine First)
                # Použijeme Outer Join, abychom měli všechna data vedle se
                merged = pd.merge(
                    df_main,
                    df_new,
                    on=key,
                    how='outer',
                    suffixes=('', '_new'), # Původní sloupce bez přípony, nové s _new
                    indicator=True
                )

                # 6. DOPLNĚNÍ DAT (Fillna)
                # Projdeme sloupce, které mají variantu "_new", a doplníme jimi prázdná místa v hlavních sloupcích
                for col in merged.columns:
                    if col.endswith('_new'):
                        original_col = col[:-4] # Odstraní "_new"
                        if original_col in merged.columns:
                            # Tady se stane magie: Pokud je v originálu prázdno, vezme se hodnota z _new
                            merged[original_col] = merged[original_col].fillna(merged[col])
                
                # Odstraníme pomocné "_new" sloupce a merge indikátor (použijeme ho jen pro status)
                merged['Status_Analýzy'] = merged.apply(lambda x: get_status(x[key], x['_merge']), axis=1)
                
                # Vyčistíme finální tabulku od pomocných sloupců
                final_cols = [c for c in merged.columns if not c.endswith('_new') and c != '_merge']
                # Dáme Status a Key na začátek
                cols_order = ['Status_Analýzy', key] + [c for c in final_cols if c not in ['Status_Analýzy', key]]
                df_final = merged[cols_order]

                # 7. KONTROLA CHYBĚJÍCÍCH HODNOT
                critical_cols = ['Material', 'Number of pieces', 'Weight (kg)']
                
                def check_completeness(row):
                    missing = []
                    for col in critical_cols:
                        if col in row.index and (pd.isna(row[col]) or str(row[col]).strip() == '' or str(row[col]).lower() == 'nan'):
                            missing.append(col)
                    if missing:
                        return f"⚠️ Chybí: {', '.join(missing)}"
                    return "OK"

                df_final.insert(1, 'Kontrola_Dat', df_final.apply(check_completeness, axis=1))

                # --- VÝSTUP ---
                st.success("Hotovo! Data byla úspěšně sjednocena.")
                
                # Statistiky
                st.write("### Statistiky")
                col_m1, col_m2 = st.columns(2)
                col_m1.metric("Celkový počet řádků", len(df_final))
                col_m2.metric("Nové (přidané) řádky", len(df_final[df_final['Status_Analýzy'] == 'NOVÉ (Přidáno)']))

                # Náhled
                st.subheader("Náhled výsledné tabulky")
                st.dataframe(df_final.head(50))

                # Export
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Final_Data')
                    
                    workbook = writer.book
                    worksheet = writer.sheets['Final_Data']
                    
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
                st.write("Tip: Zkontrolujte, zda soubory nejsou poškozené a zda obsahují správné sloupce.")
