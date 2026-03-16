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
    
    # Выбор способа ввода товара
    input_method = st.radio("Как найти товар?", ["Сканировать штрих-код", "Поиск по имени", "Ввести штрих-код вручную"])
    
    barcode = None
    
    if input_method == "Сканировать штрих-код":
        st.info("Наведи камеру на штрих-код (разреши доступ к камере в браузере)")
        camera_image = st.camera_input("Сканировать")
        if camera_image is not None:
            img = Image.open(camera_image)
            decoded_objects = decode(img)
            if decoded_objects:
                barcode = decoded_objects[0].data.decode('utf-8')
                st.success(f"Распознано: **{barcode}**")
            else:
                st.error("Штрих-код не распознан. Попробуй другой угол или введи вручную.")
    
    elif input_method == "Поиск по имени":
        if not products.empty:
            product_names = products['Name'].astype(str).tolist()
            selected_name = st.selectbox("Выбери товар из базы", [""] + product_names)
            if selected_name and selected_name != "":
                barcode_row = products[products['Name'] == selected_name]
                if not barcode_row.empty:
                    barcode = barcode_row['Barcode'].iloc[0]
                    st.info(f"Выбран товар: **{selected_name}** (штрих-код: {barcode})")
        else:
            st.warning("База товаров пуста. Добавь товары во вкладке 'Товары'.")
    
    elif input_method == "Ввести штрих-код вручную":
        barcode = st.text_input("Введи штрих-код")
    
    # Если штрих-код найден — показываем поля
    if barcode:
        # Ищем имя товара в базе
        name = "Неизвестный товар"
        if barcode in products['Barcode'].values:
            name = products[products['Barcode'] == barcode]['Name'].iloc[0]
        
        st.markdown(f"**Товар:** {name}")
        st.markdown(f"**Штрих-код:** {barcode}")
        
        expiration = st.text_input("Срок годности (формат: ДД.ММ.ГГ, например 15.12.26)", "")
        
        if st.button("Добавить в работу", type="primary"):
            if expiration.strip() == "":
                st.error("Укажи срок годности!")
            else:
                # Добавляем в InWork
                new_row = pd.DataFrame({
                    'Barcode': [barcode],
                    'Name': [name],
                    'Expiration': [expiration]
                })
                
                current_inwork = get_inwork()
                # Проверяем, нет ли уже такого товара
                if barcode in current_inwork['Barcode'].values:
                    st.warning("Этот товар уже в работе. Обновляем срок.")
                    current_inwork.loc[current_inwork['Barcode'] == barcode, 'Expiration'] = expiration
                    update_inwork(current_inwork)
                else:
                    updated_inwork = pd.concat([current_inwork, new_row], ignore_index=True)
                    update_inwork(updated_inwork)
                
                # Обновляем статус в Products (если есть)
                if barcode in products['Barcode'].values:
                    products.loc[products['Barcode'] == barcode, 'Status'] = 1
                    update_products(products)
                
                st.success("Товар успешно поставлен в работу!")
                st.balloons()  # маленький приятный эффект :)
# Остальные табы (Поставить в работу, Приемка, Управление, Настройки) — аналогично предыдущей версии, но с st.secrets
# Если нужно — я добавлю их в следующий ответ, чтобы не перегружать этот. Пока развернём базовую версию.

st.sidebar.info("Версия 1.0 — разработано с помощью Grok")
