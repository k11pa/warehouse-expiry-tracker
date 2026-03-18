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
    df = get_inwork()  # читаем один раз
    
    barcode_clean = str(barcode).strip()
    
    if barcode_clean in df['Barcode'].values:
        # Обновляем только ячейку с датой (столбец C = 3)
        row_index = df[df['Barcode'] == barcode_clean].index[0] + 2  # +2 для заголовка
        ws.update_cell(row_index, 3, expiration)
    else:
        # Добавляем новую строку
        ws.append_row([barcode_clean, name, expiration])
    
    time.sleep(2)  # обязательная задержка, чтобы Google не блокировал

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
    red = int(settings.get('RedMonths', 2))
    yellow = int(settings.get('YellowMonths', 3))
    if months_left <= 0:
        return "#ffcccc"
    if months_left < red:
        return "#ff9999"
    if months_left < yellow:
        return "#ffff99"
    return "#ffffff"

def get_settings():
    ws = sheet.worksheet("Settings")
    data = ws.get_all_records()
    return {row.get('Key', ''): row.get('Value', '') for row in data} or {'YellowMonths': '3', 'RedMonths': '2'}

# Интерфейс
st.set_page_config(page_title="Склад — Сроки годности", layout="wide")

tab2, tab1, tab3, tab4, tab5 = st.tabs(["Поставить в работу", "В работе", "Приемка + Печать", "Товары", "Настройки"])

with tab2:
    st.title("Обход склада — поставить/обновить сроки")
    st.markdown("Вводи последние 6 цифр или полный штрих-код паллета. Поле очистится автоматически после добавления.")

    products = get_products()
    
    # Поля в session_state
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
                    st.error(f"Товар **{name}** — нет в наличии (статус {status}).")
                else:
                    current_inwork = get_inwork()
                    current_expiration = st.session_state.expiration_input
                    
                    if not current_inwork.empty and 'Barcode' in current_inwork.columns:
                        current_inwork['Barcode'] = current_inwork['Barcode'].astype(str).str.strip()
                        if row['Barcode'] in current_inwork['Barcode'].values:
                            current_expiration = current_inwork[current_inwork['Barcode'] == row['Barcode']]['Expiration'].iloc[0]
                            st.session_state.expiration_input = current_expiration
                            st.info(f"Уже в работе. Текущий срок: **{current_expiration}**")
                    
                    st.markdown(f"**Товар:** {name}")
                    st.markdown(f"**Штрих-код:** {row['Barcode']}")
                    
                    expiration = st.text_input("Срок годности (ДД.ММ.ГГ)", value=st.session_state.expiration_input, placeholder="15.12.26")
                    
                    if st.button("✅ Добавить / Обновить", type="primary", use_container_width=True):
                        if not expiration.strip():
                            st.error("Укажи срок годности!")
                        else:
                            try:
                                update_or_add_inwork(row['Barcode'], name, expiration)
                                st.success("Готово! Срок обновлён или товар добавлен.")
                                time.sleep(2)  # задержка для API
                                # Очищаем оба поля
                                st.session_state.barcode_input = ""
                                st.session_state.expiration_input = ""
                                st.rerun()
                            except gspread.exceptions.APIError as e:
                                st.error("Временная ошибка Google Sheets. Подожди 30–60 секунд и попробуй снова.")
                                if st.button("Повторить попытку"):
                                    st.rerun()
            else:
                st.error(f"Штрих-код **{barcode_clean}** не найден в базе.")
                st.markdown("Обнови базу через Excel от офиса.")
        else:
            st.error("База товаров пуста. Загрузи Excel.")

# Вкладка "В работе" (без изменений)
with tab1:
    st.header("Товары в работе")
    inwork = get_inwork()
    if not inwork.empty:
        search = st.text_input("Поиск по имени / штрих-коду")
        filtered = inwork
        if search:
            search = search.strip()
            filtered = inwork[inwork['Name'].astype(str).str.contains(search, case=False, na=False) |
                              inwork['Barcode'].astype(str).str.contains(search, na=False)]
        
        filtered['ExpDate'] = filtered['Expiration'].apply(parse_date)
        filtered = filtered.sort_values(by='ExpDate')
        filtered.drop('ExpDate', axis=1, inplace=True)
        
        settings = get_settings()
        st.markdown("### Список (ближайшие сроки сверху)")
        for _, row in filtered.iterrows():
            color = get_color(row['Expiration'], settings)
            bg = f"background-color: {color}; padding: 8px; margin: 4px; border-radius: 4px;"
            st.markdown(f"<div style='{bg}'>{row['Barcode']} — {row['Name']} — {row['Expiration']}</div>", unsafe_allow_html=True)
        
        csv_all = filtered.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать весь список (CSV)", csv_all, "inwork.csv")
        
        red_filtered = filtered[filtered['Expiration'].apply(lambda x: get_color(x, settings) == 'red')]
        if not red_filtered.empty:
            csv_red = red_filtered.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать только красные", csv_red, "red_inwork.csv")
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
    st.header("Настройки")
    st.info("Функционал в разработке")

st.sidebar.info("Версия 1.6 — разработано с помощью Grok")
