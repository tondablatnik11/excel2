import streamlit as st
import pandas as pd
import io

# Nastavení stránky
st.set_page_config(page_title="Porovnávač Reportů", page_icon="⚖️", layout="wide")

st.title("⚖️ Porovnání a Doplnění Delivery")
st.markdown("""
Tato aplikace porovná **Sešit1** (hlavní log) a **Spojený Report** (nová data).
1. **Doplní** delivery, které jsou v reportu, ale chybí v Sešitu1.
2. **Označí**, která delivery nemají data v obou souborech.
""")

def clean_dn_number(df, col_name):
    """Převede číslo zakázky na text a odstraní .0 na konci"""
    if col_name in df.columns:
        return df[col_name].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    return None

def load_data(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)

# Upload sekce
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Hlavní soubor (Sešit1)")
    file_sesit = st.file_uploader("Nahrajte Sešit1", type=['xlsx', 'csv'], key="f1")

with col2:
    st.subheader("2. Nová data (Spojený report)")
    file_report = st.file_uploader("Nahrajte spojený report", type=['xlsx', 'csv'], key="f2")

if file_sesit and file_report:
    if st.button("Porovnat a Spojit"):
        with st.spinner('Analyzuji rozdíly...'):
            try:
                # Načtení
                df_sesit = load_data(file_sesit)
                df_report = load_data(file_report)

                # Definice klíčového sloupce (upravte pokud se jmenuje jinak)
                key_col = 'DN NUMBER (SAP)' 
                # V reportu se může jmenovat stejně, pokud ne, aplikace by potřebovala úpravu
                # Předpokládáme, že ve "spojeny_report" je už také 'DN NUMBER (SAP)' z minula
                # Pokud ne, zkusíme najít 'Zakázka (Delivery)'
                
                key_col_report = key_col
                if key_col not in df_report.columns and 'Zakázka (Delivery)' in df_report.columns:
                    key_col_report = 'Zakázka (Delivery)'
                
                # Čištění klíčů
                if key_col not in df_sesit.columns:
                    st.error(f"Chyba: V Sešitu1 chybí sloupec '{key_col}'")
                    st.stop()
                
                df_sesit[key_col] = clean_dn_number(df_sesit, key_col)
                df_report[key_col_report] = clean_dn_number(df_report, key_col_report)

                # MERGE (Outer Join)
                # indicator=True vytvoří sloupec '_merge', který řekne, odkud data pochází
                merged_df = pd.merge(
                    df_sesit,
                    df_report,
                    left_on=key_col,
                    right_on=key_col_report,
                    how='outer',
                    suffixes=('_Sešit1', '_Report'),
                    indicator=True
                )

                # Překlad statusů
                status_map = {
                    'left_only': 'Pouze v Sešitu1 (Chybí v reportu)',
                    'right_only': 'NOVÉ (Přidáno z reportu)',
                    'both': 'Kompletní (V obou)'
                }
                merged_df['Status_Dat'] = merged_df['_merge'].map(status_map)
                
                # Uspořádání sloupců - Status dáme na začátek
                cols = ['Status_Dat', key_col] + [c for c in merged_df.columns if c not in ['Status_Dat', key_col, '_merge']]
                merged_df = merged_df[cols]

                # --- VÝSLEDKY ---
                st.success("Analýza hotova!")
                
                # Metriky
                counts = merged_df['Status_Dat'].value_counts()
                m1, m2, m3 = st.columns(3)
                m1.metric("Kompletní v obou", counts.get('Kompletní (V obou)', 0))
                m2.metric("Chybí v Sešitu1 (Přidáno)", counts.get('NOVÉ (Přidáno z reportu)', 0), delta="Nová data")
                m3.metric("Chybí v Reportu", counts.get('Pouze v Sešitu1 (Chybí v reportu)', 0), delta_color="inverse")

                # Zobrazení nekompletních (co uživatele zajímá nejvíc)
                st.subheader("⚠️ Delivery, které nemají všechny hodnoty")
                incomplete_df = merged_df[merged_df['Status_Dat'] != 'Kompletní (V obou)']
                st.write(f"Nalezeno {len(incomplete_df)} nekompletních záznamů.")
                st.dataframe(incomplete_df.head(50), use_container_width=True)

                # Export
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    merged_df.to_excel(writer, index=False, sheet_name='Porovnani')
                    
                    # Formátování
                    workbook = writer.book
                    worksheet = writer.sheets['Porovnani']
                    red_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                    green_format = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
                    
                    # Podmíněné formátování pro sloupec Status
                    worksheet.conditional_format('A2:A99999', {
                        'type': 'text',
                        'criteria': 'containing',
                        'value': 'NOVÉ',
                        'format': green_format
                    })
                    worksheet.conditional_format('A2:A99999', {
                        'type': 'text',
                        'criteria': 'containing',
                        'value': 'Chybí',
                        'format': red_format
                    })

                output.seek(0)
                st.download_button(
                    label="📥 Stáhnout kompletní analýzu (.xlsx)",
                    data=output,
                    file_name="porovnani_delivery.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                st.error(f"Chyba: {e}")
