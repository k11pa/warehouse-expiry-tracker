import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Подключение к той же базе
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info.to_dict(), SCOPE)
CLIENT = gspread.authorize(creds)
SHEET_ID = "1q8RdFS_XBl0N7QhdBITQzCQXCLGEo2kkLEpDc3Jn5BM"
sheet = CLIENT.open_by_key(SHEET_ID)

def get_inwork():
    ws = sheet.worksheet("InWork")
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty and 'Barcode' in df.columns:
        df['Barcode'] = df['Barcode'].astype(str).str.strip()
    return df

def get_settings():
    ws = sheet.worksheet("Settings")
    data = ws.get_all_records()
    return {row.get('Key', ''): row.get('Value', '') for row in data} or {'YellowMonths': '3', 'RedMonths': '2'}

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
    if months_left <= 0 or months_left < red:
        return "#ff9999"   # красный
    if months_left < yellow:
        return "#ffff99"   # жёлтый
    return "#ffffff"       # белый

# Интерфейс
st.set_page_config(page_title="Отчёт по срокам в работе", layout="wide")
st.title("Товары в работе")
st.markdown("Обновляется автоматически. Сортировка по клику на заголовок.")

inwork = get_inwork()

if not inwork.empty:
    search = st.text_input("Поиск по имени / штрих-коду / сроку", "")
    filtered = inwork
    if search:
        search = search.strip()
        filtered = inwork[
            inwork['Name'].astype(str).str.contains(search, case=False, na=False) |
            inwork['Barcode'].astype(str).str.contains(search, na=False) |
            inwork['Expiration'].astype(str).str.contains(search, na=False)
        ]
    
    # Сортировка по сроку (ближайшие сверху)
    def sort_key(date_str):
        exp = parse_date(date_str)
        return exp if exp else datetime.max
    
    filtered = filtered.sort_values(by='Expiration', key=lambda x: x.apply(sort_key))
    
    settings = get_settings()
    
    # Окраска строк
    def highlight_row(row):
        exp = parse_date(row['Expiration'])
        if not exp:
            return [''] * len(row)
        months_left = relativedelta(exp, datetime.now()).months + (relativedelta(exp, datetime.now()).years * 12)
        if months_left <= 0 or months_left < int(settings.get('RedMonths', 2)):
            return ['background-color: #ff9999'] * len(row)  # красный
        if months_left < int(settings.get('YellowMonths', 3)):
            return ['background-color: #ffff99'] * len(row)  # жёлтый
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
    
    # Экспорт
    csv_all = filtered.to_csv(index=False).encode('utf-8')
    st.download_button("Скачать весь список (CSV)", csv_all, "в_работе.csv", "text/csv")
    
    red_filtered = filtered[filtered['Expiration'].apply(lambda x: get_color(x, settings) == '#ff9999')]
    if not red_filtered.empty:
        csv_red = red_filtered.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать только красные", csv_red, "красные.csv", "text/csv")
else:
    st.info("Пока нет товаров в работе.")

st.sidebar.info("Отчёт только для просмотра · Данные из InWork · Обновляется в реальном времени")
