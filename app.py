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

# Настройки
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info.to_dict(), SCOPE)
CLIENT = gspread.authorize(creds)
SHEET_ID = "1q8RdFS_XBl0N7QhdBITQzCQXCLGEo2kkLEpDc3Jn5BM"
sheet = CLIENT.open_by_key(SHEET_ID)

# Функции для Sheets
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

# Парсинг даты
def parse_date(date_str):
    try:
        d, m, y = map(int, date_str.split('.'))
        return datetime(2000 + y, m, d)
    except:
        return None

# Цвет по сроку
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
    return "white"

# Интерфейс
st.set_page_config(page_title="Склад — Сроки годности", layout="wide")
st.title("Управление сроками годности на складе")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["В работе", "Поставить в работу", "Приемка + Печать", "Товары", "Настройки"])

with tab1:
    st.header("Товары в работе")
    inwork = get_inwork()
    if not inwork.empty:
        search = st.text_input("Поиск по имени / штрих-коду")
        filtered = inwork
        if search:
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

with tab2:
    st.header("Обход склада — поставить/обновить в работе")
    
    products = get_products()
    
    input_method = st.radio("Способ ввода:", 
                            ["Сфоткать штрих-код", "Ввести штрих-код вручную"], 
                            horizontal=True)
    
    barcode = None
    name = None
    current_expiration = ""
    
    if input_method == "Сфоткать штрих-код":
        st.info("Наведи камеру на штрих-код паллета → нажми кнопку")
        camera_image = st.camera_input("Сделать фото", key="warehouse_scanner")
        
        if camera_image:
            img = Image.open(camera_image)
            decoded = decode(img)
            if decoded:
                barcode = decoded[0].data.decode('utf-8')
                st.success(f"Считано: **{barcode}**")
            else:
                st.warning("Не распознан. Попробуй другой угол.")
    
    elif input_method == "Ввести штрих-код вручную":
        barcode = st.text_input("Введи штрих-код паллета")
    
    if barcode:
        if not products.empty and barcode in products['Barcode'].values:
            row = products[products['Barcode'] == barcode].iloc[0]
            name = row['Name']
            status = row.get('Status', '')  # Получаем статус
            
            if '2' in status:  # Если ^^^^^^^^^2 или просто 2
                st.error(f"Товар **{name}** — нет в наличии (статус {status}).")
            else:
                current_inwork = get_inwork()
                if barcode in current_inwork['Barcode'].values:
                    current_expiration = current_inwork[current_inwork['Barcode'] == barcode]['Expiration'].iloc[0]
                    st.info(f"Уже в работе. Текущий срок: **{current_expiration}**")
                
                st.markdown(f"**Товар:** {name}")
                st.markdown(f"**Штрих-код:** {barcode}")
                
                expiration = st.text_input("Срок годности (ДД.ММ.ГГ)", value=current_expiration, placeholder="15.12.26")
                
                if st.button("✅ Добавить/Обновить", type="primary"):
                    if not expiration.strip():
                        st.error("Укажи срок!")
                    else:
                        new_row = pd.DataFrame({'Barcode': [barcode], 'Name': [name], 'Expiration': [expiration]})
                        if barcode in current_inwork['Barcode'].values:
                            current_inwork.loc[current_inwork['Barcode'] == barcode, 'Expiration'] = expiration
                            update_inwork(current_inwork)
                            st.success("Обновлено!")
                        else:
                            update_inwork(pd.concat([current_inwork, new_row], ignore_index=True))
                            st.success("Добавлено в работу!")
                        
                        st.balloons()
                        st.rerun()  # Авто-перезапуск для следующего паллета
        else:
            st.error("Товар не найден в базе. Обнови Excel от офиса.")

with tab3:
    # (твой текущий код для приемки и печати, не меняем пока)
