import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Подключение к тому же Google Sheet
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info.to_dict(), SCOPE)
CLIENT = gspread.authorize(creds)
SHEET_ID = "1q8RdFS_XBl0N7QhdBITQzCQXCLGEo2kkLEpDc3Jn5BM"
sheet = CLIENT.open_by_key(SHEET_ID)

# Функции
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
    if months_left <= 0:
        return "#ffcccc"  # просрочен
    if months_left < red:
        return "#ff9999"  # красный
    if months_left < yellow:
        return "#ffff99"  # жёлтый
    return "#ffffff"  # белый

# Интерфейс
st.set_page_config(page_title="Товары в работе — Отчёт", layout="wide")
st.title("Товары в работе")
st.markdown("Только актуальные товары на 0-м этаже. Цвета показывают срочность срока годности.")

inwork = get_inwork()

if not inwork.empty:
    search = st.text_input("Поиск по имени или штрих-коду", "")
    filtered = inwork
    if search:
        search = search.strip()
        filtered = inwork[
            inwork['Name'].astype(str).str.contains(search, case=False, na=False) |
            inwork['Barcode'].astype(str).str.contains(search, na=False)
        ]
    
    # Сортировка по сроку
    filtered['ExpDate'] = filtered['Expiration'].apply(parse_date)
    filtered = filtered.sort_values(by='ExpDate')
    filtered = filtered.drop(columns=['ExpDate'], errors='ignore')
    
    settings = get_settings()
    
    st.markdown("### Список товаров (ближайшие сроки сверху)")
    for _, row in filtered.iterrows():
        bg = get_color(row['Expiration'], settings)
        st.markdown(
            f"<div style='background-color:{bg}; padding:12px; margin:8px; border-radius:8px; border:1px solid #ccc; font-size:16px;'>"
            f"<strong>{row['Barcode']}</strong> — {row['Name']} — <strong>{row['Expiration']}</strong>"
            f"</div>",
            unsafe_allow_html=True
        )
    
    # Экспорт для начальства
    csv = filtered.to_csv(index=False).encode('utf-8')
    st.download_button("Скачать отчёт в CSV", csv, "в_работе_отчет.csv", "text/csv")
    
else:
    st.info("Пока нет товаров в работе.")

st.sidebar.info("Отчёт только для просмотра · Обновляется в реальном времени")
