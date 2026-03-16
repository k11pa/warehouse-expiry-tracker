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
    st.header("Обход склада — поставить/обновить в работе")
    
    products = get_products()
    
    # Большая кнопка для быстрого сканирования
    st.markdown("### Сканируй паллеты на 0-м этаже")
    
    input_method = st.radio("Способ ввода:", 
                            ["Сфоткать штрих-код (рекомендую)", "Ввести штрих-код вручную"], 
                            horizontal=True)
    
    barcode = None
    current_expiration = ""
    
    if input_method == "Сфоткать штрих-код (рекомендую)":
        st.info("Наведи камеру на штрих-код паллета → нажми кнопку ниже")
        camera_image = st.camera_input("Сфотографировать штрих-код", key="warehouse_scanner")
        
        if camera_image:
            img = Image.open(camera_image)
            decoded = decode(img)
            if decoded:
                barcode = decoded[0].data.decode('utf-8')
                st.success(f"Считано: **{barcode}**")
            else:
                st.warning("Не распознан. Попробуй ближе/дальше или другой угол.")
    
    elif input_method == "Ввести штрих-код вручную":
        barcode = st.text_input("Введи штрих-код паллета")
    
    # ──────────────────────────────────────────────
    if barcode:
        if not products.empty and barcode in products['Barcode'].values:
            row = products[products['Barcode'] == barcode].iloc[0]
            name = row['Name']
            status = row.get('Status', 1)  # если столбец есть
            
            if status != 1:
                st.error(f"Товар **{name}** — статус {status} (нет в наличии). Нельзя добавить.")
            else:
                # Показываем текущий срок, если товар уже в работе
                current_inwork = get_inwork()
                if barcode in current_inwork['Barcode'].values:
                    current_expiration = current_inwork[current_inwork['Barcode'] == barcode]['Expiration'].iloc[0]
                    st.info(f"Товар уже в работе. Текущий срок: **{current_expiration}**")
                
                st.markdown(f"**Товар:** {name}")
                st.markdown(f"**Штрих-код:** {barcode}")
                
                expiration = st.text_input("Срок годности (ДД.ММ.ГГ)", 
                                         value=current_expiration, 
                                         placeholder="15.12.26",
                                         key=f"exp_{barcode}")
                
                if st.button("✅ Обновить / Добавить в работу", type="primary", use_container_width=True):
                    if not expiration.strip():
                        st.error("Укажи срок!")
                    else:
                        new_row = pd.DataFrame({'Barcode': [barcode], 'Name': [name], 'Expiration': [expiration]})
                        if barcode in current_inwork['Barcode'].values:
                            current_inwork.loc[current_inwork['Barcode'] == barcode, 'Expiration'] = expiration
                            update_inwork(current_inwork)
                            st.success("Срок обновлён!")
                        else:
                            update_inwork(pd.concat([current_inwork, new_row], ignore_index=True))
                            st.success("Товар добавлен в работу!")
                        
                        st.balloons()
                        # Чтобы сразу можно было сканировать следующий — очищаем поле
                        st.rerun()  # перезагружает страницу для нового сканирования
        else:
            st.error(f"Штрих-код **{barcode}** не найден в базе.")
            st.markdown("Обнови базу через Excel от офиса.")
