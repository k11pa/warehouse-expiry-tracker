import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Подключение к базе (точно такое же, как в app.py)
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_info = st.secrets["google_credentials"]  # ← если здесь ошибка — замени на "gcp_service_account"
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
    if months_left <= 0:
        return "#ffcccc"  # просрочен
    if months_left < red:
        return "#ff9999"  # красный
    if months_left < yellow:
        return "#ffff99"  # жёлтый
    return "#ffffff"  # белый

# Интерфейс — только для просмотра
st.set_page_config(page_title="Отчёт по срокам — только просмотр", layout="wide")
st.title("Товары в работе")
st.markdown("Актуальный список товаров на 0-м этаже. Обновляется автоматически.")

filter_option = st.selectbox(
    "Показать:",
    ["Всё сразу", "Только красные (критические)", "Только жёлтые", "Только нормальные (зелёные)"],
    index=0
)

inwork = get_inwork()

if not inwork.empty:
    # Поиск
    search = st.text_input("Поиск по имени или штрих-коду", "")

    # Подготовка данных
    settings = get_settings()
    inwork['ExpDate'] = inwork['Expiration'].apply(parse_date)
    inwork['Color'] = inwork['Expiration'].apply(lambda x: get_color(x, settings))

    filtered = inwork.copy()

    if search:
        search = search.strip()
        filtered = filtered[
            filtered['Name'].astype(str).str.contains(search, case=False, na=False) |
            filtered['Barcode'].astype(str).str.contains(search, na=False)
        ]

    # Фильтр по цвету
    if filter_option == "Только красные (критические)":
        filtered = filtered[filtered['Color'].isin(["#ff9999", "#ffcccc"])]
    elif filter_option == "Только жёлтые":
        filtered = filtered[filtered['Color'] == "#ffff99"]
    elif filter_option == "Только нормальные (зелёные)":
        filtered = filtered[filtered['Color'] == "#ffffff"]

    # Сортировка от меньшей даты к большей (ближайшие сверху)
    filtered = filtered.sort_values(by='ExpDate')

    # Вывод списка
    st.markdown(f"**Найдено товаров: {len(filtered)}**")

    for _, row in filtered.iterrows():
        bg = row['Color']
        st.markdown(
            f"<div style='background-color:{bg}; padding:12px; margin:8px; border-radius:8px; border:1px solid #ccc; font-size:16px;'>"
            f"<strong>{row['Barcode']}</strong> — {row['Name']} — <strong>{row['Expiration']}</strong>"
            f"</div>",
            unsafe_allow_html=True
        )

    # Экспорт
    export_df = filtered.drop(columns=['ExpDate', 'Color'], errors='ignore')
    csv = export_df.to_csv(index=False).encode('utf-8')
    st.download_button("Скачать отчёт в CSV", csv, "отчет_в_работе.csv", "text/csv")

else:
    st.info("Пока нет товаров в работе.")

st.sidebar.info("Отчёт только для просмотра · Данные из InWork · Обновляется в реальном времени")
