import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from PIL import Image
from pyzbar.pyzbar import decode
import json
import io

# === Настройки ===
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Загружаем credentials из secrets (Streamlit Cloud)
creds_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info.to_dict(), SCOPE)
CLIENT = gspread.authorize(creds)

SHEET_ID = "1q8RdFS_XBl0N7QhdBITQzCQXCLGEo2kkLEpDc3Jn5BM"
sheet = CLIENT.open_by_key(SHEET_ID)

# Функции работы с листами (как раньше)
def get_products():
    ws = sheet.worksheet("Products")
    return pd.DataFrame(ws.get_all_records())

def update_products(df):
    ws = sheet.worksheet("Products")
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())

def get_inwork():
    ws = sheet.worksheet("InWork")
    return pd.DataFrame(ws.get_all_records())

def update_inwork(df):
    ws = sheet.worksheet("InWork")
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())

def get_settings():
    ws = sheet.worksheet("Settings")
    data = ws.get_all_records()
    return {row.get('Key', ''): row.get('Value', '') for row in data} or {'YellowMonths': '3', 'RedMonths': '2'}

def update_settings(settings):
    ws = sheet.worksheet("Settings")
    ws.clear()
    data = [['Key', 'Value']] + [[k, v] for k, v in settings.items()]
    ws.update(data)

def parse_date(date_str):
    try:
        d, m, y = map(int, date_str.split('.'))
        return datetime(2000 + y, m, d)
    except:
        return None

def get_color(exp_str, settings):
    exp = parse_date(exp_str)
    if not exp:
        return ""
    months_left = relativedelta(exp, datetime.now()).months + (relativedelta(exp, datetime.now()).years * 12)
    red = int(settings.get('RedMonths', 2))
    yellow = int(settings.get('YellowMonths', 3))
    if months_left < red:
        return "red"
    if months_left < yellow:
        return "yellow"
    return ""

# === Интерфейс ===
st.set_page_config(page_title="Склад — Сроки годности", layout="wide")
st.title("Управление сроками годности на складе")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["В работе", "Поставить в работу", "Приемка + Печать", "Товары", "Настройки"])

# Tab 1 — В работе (как раньше, с цветами и сортировкой)
with tab1:
    st.header("Товары в работе")
    inwork = get_inwork()
    if not inwork.empty:
        search = st.text_input("Поиск по имени / штрих-коду")
        filtered = inwork
        if search:
            filtered = inwork[inwork['Name'].astype(str).str.contains(search, case=False, na=False) |
                              inwork['Barcode'].astype(str).str.contains(search, na=False)]
        
        filtered = filtered.sort_values(by='Expiration', key=lambda x: pd.to_datetime(x.apply(parse_date), errors='coerce'))
        
        settings = get_settings()
        st.markdown("### Список (ближайшие сроки сверху)")
        for _, row in filtered.iterrows():
            color = get_color(row['Expiration'], settings)
            bg = f"background-color: {color};" if color else ""
            st.markdown(f"<div style='{bg} padding:8px; margin:4px; border-radius:4px;'>{row['Barcode']} — {row['Name']} — {row['Expiration']}</div>", unsafe_allow_html=True)
        
        # Экспорт
        csv_all = filtered.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать весь список (CSV)", csv_all, "в_работе.csv", "text/csv")
        
        red_only = filtered[filtered['Expiration'].apply(lambda x: get_color(x, settings) == "red")]
        if not red_only.empty:
            csv_red = red_only.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать только красные (просрочка скоро)", csv_red, "красные.csv", "text/csv")
    else:
        st.info("Пока нет товаров в работе.")

with tab2:
    st.header("Поставить товар в работу")
    
    products = get_products()
    
    input_method = st.radio("Как найти товар?", 
                            ["Сфоткать штрих-код (быстро)", "Поиск по имени", "Ввести штрих-код вручную"])
    
    barcode = None
    name = "Неизвестный товар"
    
    if input_method == "Сфоткать штрих-код (быстро)":
        st.info("Наведи камеру на штрих-код и нажми кнопку ниже для распознавания")
        
        camera_image = st.camera_input("Сделать фото штрих-кода", key="camera_scanner")
        
        if camera_image:
            img = Image.open(camera_image)
            decoded = decode(img)
            if decoded:
                barcode = decoded[0].data.decode('utf-8')
                st.success(f"✅ Распознано автоматически: **{barcode}**")
            else:
                st.warning("Не видно штрих-кода. Попробуй:")
                st.markdown("- Другой угол или расстояние")
                st.markdown("- Лучшее освещение")
                st.markdown("- Чётче сфокусировать")
    
    elif input_method == "Поиск по имени":
        if not products.empty:
            selected = st.selectbox("Выбери товар", [""] + products['Name'].astype(str).tolist())
            if selected:
                row = products[products['Name'] == selected].iloc[0]
                barcode = row['Barcode']
                name = row['Name']
                st.info(f"Выбран: **{name}** (штрих-код {barcode})")
        else:
            st.warning("База товаров пуста. Добавь во вкладке «Товары».")
    
    elif input_method == "Ввести штрих-код вручную":
        barcode = st.text_input("Введи штрих-код полностью")
    
    # Общая часть — если barcode найден любым способом
    if barcode:
        # Ищем имя, если есть в базе
        if not products.empty and barcode in products['Barcode'].values:
            name = products[products['Barcode'] == barcode]['Name'].iloc[0]
        
        st.markdown(f"**Товар:** {name}")
        st.markdown(f"**Штрих-код:** {barcode}")
        
        expiration = st.text_input("Срок годности (ДД.ММ.ГГ)", placeholder="15.12.26")
        
        if st.button("✅ Добавить в работу", type="primary"):
            if not expiration.strip():
                st.error("Обязательно укажи срок!")
            else:
                new_row = pd.DataFrame({'Barcode': [barcode], 'Name': [name], 'Expiration': [expiration]})
                current = get_inwork()
                
                if barcode in current['Barcode'].values:
                    current.loc[current['Barcode'] == barcode, 'Expiration'] = expiration
                    update_inwork(current)
                    st.info("Срок обновлён для существующего товара")
                else:
                    update_inwork(pd.concat([current, new_row], ignore_index=True))
                    st.success("Новый товар добавлен в работу!")
                
                st.balloons()
