import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time

# Подключение
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info.to_dict(), SCOPE)
CLIENT = gspread.authorize(creds)
SHEET_ID = "1q8RdFS_XBl0N7QhdBITQzCQXCLGEo2kkLEpDc3Jn5BM"
sheet = CLIENT.open_by_key(SHEET_ID)

# Функции
def get_products():
    ws = sheet.worksheet("Products")
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty and 'Barcode' in df.columns:
        df['Barcode'] = df['Barcode'].astype(str).str.strip()
    return df

def get_inwork():
    ws = sheet.worksheet("InWork")
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty and 'Barcode' in df.columns:
        df['Barcode'] = df['Barcode'].astype(str).str.strip()
    return df

def update_or_add_inwork(barcode, name, expiration):
    ws = sheet.worksheet("InWork")
    df = get_inwork()
    
    barcode_clean = str(barcode).strip()
    
    if barcode_clean in df['Barcode'].values:
        row_index = df[df['Barcode'] == barcode_clean].index[0] + 2
        ws.update_cell(row_index, 3, expiration)
    else:
        ws.append_row([barcode_clean, name, expiration])
    
    time.sleep(1)

def remove_from_inwork(barcode):
    """Удаляет товар из InWork по баркоду"""
    ws = sheet.worksheet("InWork")
    df = get_inwork()
    barcode_clean = str(barcode).strip()
    
    if barcode_clean in df['Barcode'].values:
        row_index = df[df['Barcode'] == barcode_clean].index[0] + 2
        ws.delete_rows(row_index)
        time.sleep(1)

def parse_date(date_str):
    try:
        d, m, y = map(int, date_str.split('.'))
        return datetime(2000 + y, m, d)
    except:
        return None

def get_color(exp_str, settings):
    exp = parse_date(exp_str)
    if not exp:
        return "#ffffff"
    months_left = relativedelta(exp, datetime.now()).months + (relativedelta(exp, datetime.now()).years * 12)
    red = float(settings.get('RedMonths', 2.0))
    yellow = float(settings.get('YellowMonths', 3.0))
    if months_left <= 0 or months_left < red:
        return "#ff9999"
    if months_left < yellow:
        return "#ffff99"
    return "#ffffff"

def get_settings():
    ws = sheet.worksheet("Settings")
    data = ws.get_all_records()
    return {row.get('Key', ''): row.get('Value', '') for row in data} or {'YellowMonths': '3.0', 'RedMonths': '2.0'}

def update_settings(settings):
    ws = sheet.worksheet("Settings")
    ws.clear()
    data = [['Key', 'Value']] + [[k, v] for k, v in settings.items()]
    ws.update(data)

# Интерфейс
st.set_page_config(page_title="Склад — Сроки годности", layout="wide")

tab2, tab1, tab3, tab4, tab5 = st.tabs(["Поставить в работу", "В работе", "Приемка + Печать", "Товары", "Настройки"])

with tab2:
    st.title("Обход склада — обновить сроки при спуске паллета")
    st.markdown("Вводи последние 6 цифр или полный штрих-код. Поля очистятся автоматически.")

    products = get_products()
    
    if 'barcode_input' not in st.session_state:
        st.session_state.barcode_input = ""
    if 'expiration_input' not in st.session_state:
        st.session_state.expiration_input = ""
    
    barcode_input = st.text_input(
        "Введи последние 6 цифр или полный штрих-код",
        value=st.session_state.barcode_input,
        key="barcode_input_key"
    )
    
    barcode = barcode_input.strip() if barcode_input else None
    
    if barcode:
        barcode_clean = barcode
        
        if not products.empty:
            products['Barcode'] = products['Barcode'].astype(str).str.strip()
            
            if len(barcode_clean) == 6:
                matching = products[products['Barcode'].str[-6:] == barcode_clean]
            else:
                matching = products[products['Barcode'] == barcode_clean]
            
            if not matching.empty:
                row = matching.iloc[0]
                name = row['Name']
                status = str(row.get('Status', '')).strip()
                
                if '2' in status:
                    st.error(f"Товар **{name}** — нет в наличии (статус 2).")
                    # Автоматически удаляем из InWork
                    remove_from_inwork(row['Barcode'])
                    st.success("Товар удалён из списка 'В работе', так как он закончился.")
                    st.session_state.barcode_input = ""
                    st.session_state.expiration_input = ""
                else:
                    current_inwork = get_inwork()
                    current_expiration = st.session_state.expiration_input
                    
                    if not current_inwork.empty and 'Barcode' in current_inwork.columns:
                        current_inwork['Barcode'] = current_inwork['Barcode'].astype(str).str.strip()
                        if row['Barcode'] in current_inwork['Barcode'].values:
                            current_expiration = current_inwork[current_inwork['Barcode'] == row['Barcode']]['Expiration'].iloc[0]
                            st.session_state.expiration_input = current_expiration
                    
                    st.markdown(f"**Товар:** {name}")
                    st.markdown(f"**Штрих-код:** {row['Barcode']}")
                    
                    expiration = st.text_input("Срок годности (ДД.ММ.ГГ)", value=st.session_state.expiration_input, placeholder="15.12.26")
                    
                    if st.button("✅ Добавить / Обновить", type="primary", use_container_width=True):
                        if not expiration.strip():
                            st.error("Укажи срок годности!")
                        else:
                            update_or_add_inwork(row['Barcode'], name, expiration)
                            st.success("Готово!")
                            time.sleep(1)
                            st.session_state.barcode_input = ""
                            st.session_state.expiration_input = ""
            else:
                st.error(f"Штрих-код **{barcode_clean}** не найден.")
                st.markdown("Обнови базу через Excel.")
        else:
            st.error("База пуста. Загрузи Excel.")
    else:
        st.info("Введи код паллета для поиска.")

with tab1:
    st.header("Товары в работе")
    inwork = get_inwork()
    
    if not inwork.empty:
        search = st.text_input("Поиск по имени / штрих-коду / сроку")
        filtered = inwork
        if search:
            search = search.strip()
            filtered = inwork[
                inwork['Name'].astype(str).str.contains(search, case=False, na=False) |
                inwork['Barcode'].astype(str).str.contains(search, na=False) |
                inwork['Expiration'].astype(str).str.contains(search, na=False)
            ]
        
        def sort_key(date_str):
            exp = parse_date(date_str)
            return exp if exp else datetime.max
        
        filtered = filtered.sort_values(by='Expiration', key=lambda x: x.apply(sort_key))
        
        settings = get_settings()
        
        def highlight_row(row):
            exp = parse_date(row['Expiration'])
            if not exp:
                return [''] * len(row)
            months_left = relativedelta(exp, datetime.now()).months + (relativedelta(exp, datetime.now()).years * 12)
            if months_left <= 0 or months_left < float(settings.get('RedMonths', 2.0)):
                return ['background-color: #ff9999'] * len(row)
            if months_left < float(settings.get('YellowMonths', 3.0)):
                return ['background-color: #ffff99'] * len(row)
            return [''] * len(row)
        
        styled = filtered.style.apply(highlight_row, axis=1)
        
        st.dataframe(
            styled,
            use_container_width=True,
            column_config={
                "Barcode": st.column_config.TextColumn("Штрих-код", width="medium"),
                "Name": st.column_config.TextColumn("Название товара", width="large"),
                "Expiration": st.column_config.TextColumn("Срок годности", width="medium"),
            }
        )
        
        csv_all = filtered.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button("Скачать весь список (CSV)", csv_all, "в_работе.csv", "text/csv")
        
        red_filtered = filtered[filtered['Expiration'].apply(lambda x: get_color(x, settings) == '#ff9999')]
        if not red_filtered.empty:
            csv_red = red_filtered.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button("Скачать только красные", csv_red, "красные.csv", "text/csv")
    else:
        st.info("Пока нет товаров в работе.")

# Заглушки
with tab3:
    st.header("Приемка + Печать")
    st.info("Функционал в разработке")

with tab4:
    st.header("Товары")
    st.info("Функционал в разработке")

with tab5:
    st.header("Настройки цветов сроков годности")
    st.markdown("Настраивай пороги отдельно, но жёлтый всегда ≥ красный.")

    settings = get_settings()
    
    red_months = float(settings.get('RedMonths', 2.0))
    yellow_months = float(settings.get('YellowMonths', 3.0))
    
    col1, col2 = st.columns(2)
    
    with col1:
        new_red = st.slider(
            "Красный: меньше (месяцев)",
            min_value=0.5,
            max_value=12.0,
            value=red_months,
            step=0.5,
            key="red_slider"
        )
    
    with col2:
        new_yellow = st.slider(
            "Жёлтый: меньше (месяцев)",
            min_value=new_red,
            max_value=12.0,
            value=max(yellow_months, new_red),
            step=0.5,
            key="yellow_slider"
        )
    
    if st.button("Сохранить настройки", type="primary", use_container_width=True):
        new_settings = {
            'RedMonths': str(new_red),
            'YellowMonths': str(new_yellow)
        }
        update_settings(new_settings)
        st.success(f"Сохранено! Красный < {new_red} мес, жёлтый < {new_yellow} мес")
        st.rerun()

st.sidebar.info("Версия 1.8 — разработано с помощью Grok")
