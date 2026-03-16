import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from PIL import Image
from pyzbar.pyzbar import decode

# Настройки подключения к Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info.to_dict(), SCOPE)
CLIENT = gspread.authorize(creds)
SHEET_ID = "1q8RdFS_XBl0N7QhdBITQzCQXCLGEo2kkLEpDc3Jn5BM"
sheet = CLIENT.open_by_key(SHEET_ID)

# Функции работы с таблицами
def get_products():
    ws = sheet.worksheet("Products")
    df = pd.DataFrame(ws.get_all_records())
    # Приводим Barcode к строке сразу
    if not df.empty and 'Barcode' in df.columns:
        df['Barcode'] = df['Barcode'].astype(str).str.strip()
    return df

def get_inwork():
    ws = sheet.worksheet("InWork")
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty and 'Barcode' in df.columns:
        df['Barcode'] = df['Barcode'].astype(str).str.strip()
    return df

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

# Парсинг даты ДД.ММ.ГГ → datetime
def parse_date(date_str):
    try:
        d, m, y = map(int, date_str.split('.'))
        return datetime(2000 + y, m, d)
    except:
        return None

# Цвет строки по оставшимся месяцам
def get_color(exp_str, settings):
    exp = parse_date(exp_str)
    if not exp:
        return ""
    months_left = relativedelta(exp, datetime.now()).months + (relativedelta(exp, datetime.now()).years * 12)
    red = int(settings.get('RedMonths', 2))
    yellow = int(settings.get('YellowMonths', 3))
    if months_left <= 0:
        return "#ffcccc"  # просрочен — светло-красный
    if months_left < red:
        return "#ff9999"  # красный
    if months_left < yellow:
        return "#ffff99"  # жёлтый
    return "#ffffff"  # белый

# ──────────────────────────────────────────────
# Основной интерфейс
# ──────────────────────────────────────────────

st.set_page_config(page_title="Склад — Сроки годности", layout="wide")
st.title("Управление сроками годности на складе")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["В работе", "Поставить в работу", "Приемка + Печать", "Товары", "Настройки"])

# Вкладка 1 — Товары в работе
with tab1:
    st.header("Товары в работе")
    inwork = get_inwork()
    
    if not inwork.empty:
        search = st.text_input("Поиск по имени или штрих-коду")
        filtered = inwork
        if search:
            search = search.strip()
            filtered = inwork[
                inwork['Name'].astype(str).str.contains(search, case=False, na=False) |
                inwork['Barcode'].astype(str).str.contains(search, na=False)
            ]
        
        # Сортировка по сроку (ближайшие сверху)
        filtered['ExpDate'] = filtered['Expiration'].apply(parse_date)
        filtered = filtered.sort_values(by='ExpDate')
        filtered = filtered.drop(columns=['ExpDate'], errors='ignore')
        
        settings = get_settings()
        
        st.markdown("### Список (ближайшие сроки сверху)")
        for _, row in filtered.iterrows():
            bg = get_color(row['Expiration'], settings)
            st.markdown(
                f"<div style='background-color:{bg}; padding:10px; margin:6px; border-radius:6px; border:1px solid #ddd;'>"
                f"<strong>{row['Barcode']}</strong> — {row['Name']} — <strong>{row['Expiration']}</strong>"
                f"</div>",
                unsafe_allow_html=True
            )
        
        # Экспорт
        csv_all = filtered.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать весь список (CSV)", csv_all, "в_работе.csv", "text/csv")
        
        red_only = filtered[filtered['Expiration'].apply(lambda x: get_color(x, settings) in ['#ff9999', '#ffcccc'])]
        if not red_only.empty:
            csv_red = red_only.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать только просроченные/красные", csv_red, "красные.csv", "text/csv")
    else:
        st.info("Пока нет товаров в работе. Добавляй через сканирование!")

# Вкладка 2 — Обход склада (основная для тебя сейчас)
with tab2:
    st.header("Обход склада — поставить/обновить в работе")
    st.markdown("Сканируй паллеты на 0-м этаже и сразу обновляй сроки годности")
    
    products = get_products()
    
    input_method = st.radio("Способ ввода:", 
                            ["Сфоткать штрих-код", "Ввести штрих-код вручную"],
                            horizontal=True)
    
    barcode = None
    
    if input_method == "Сфоткать штрих-код":
        st.info("Наведи камеру → нажми кнопку для распознавания")
        camera_image = st.camera_input("Сфотографировать штрих-код", key="scan_key")
        
        if camera_image:
            img = Image.open(camera_image)
            decoded = decode(img)
            if decoded:
                barcode = decoded[0].data.decode('utf-8').strip()
                st.success(f"Считано: **{barcode}**")
            else:
                st.warning("Не распознан. Попробуй другой угол или освещение.")
    
    elif input_method == "Ввести штрих-код вручную":
        barcode = st.text_input("Введи штрих-код паллета полностью")
    
    # Основная логика обработки найденного штрих-кода
    if barcode:
        barcode_clean = str(barcode).strip()
        
        # Приводим базу к строкам без пробелов
        if not products.empty:
            products['Barcode_clean'] = products['Barcode'].astype(str).str.strip()
            
            if barcode_clean in products['Barcode_clean'].values:
                row = products[products['Barcode_clean'] == barcode_clean].iloc[0]
                name = row['Name']
                status = str(row.get('Status', '')).strip()
                
                if '2' in status or '^^^^^^^^^^2' in status:
                    st.error(f"Товар **{name}** — нет в наличии (статус: {status}).")
                else:
                    # Проверяем, есть ли уже в работе
                    current_inwork = get_inwork()
                    current_expiration = ""
                    if not current_inwork.empty and 'Barcode' in current_inwork.columns:
                        current_inwork['Barcode'] = current_inwork['Barcode'].astype(str).str.strip()
                        if barcode_clean in current_inwork['Barcode'].values:
                            current_expiration = current_inwork[current_inwork['Barcode'] == barcode_clean]['Expiration'].iloc[0]
                            st.info(f"Уже в работе. Текущий срок: **{current_expiration}**")
                    
                    st.markdown(f"**Товар:** {name}")
                    st.markdown(f"**Штрих-код:** {barcode_clean}")
                    
                    expiration = st.text_input("Срок годности (ДД.ММ.ГГ)", 
                                             value=current_expiration,
                                             placeholder="15.12.26",
                                             key=f"exp_{barcode_clean}")
                    
                    if st.button("✅ Добавить / Обновить", type="primary", use_container_width=True):
                        if not expiration.strip():
                            st.error("Обязательно укажи срок годности!")
                        else:
                            new_row = pd.DataFrame({
                                'Barcode': [barcode_clean],
                                'Name': [name],
                                'Expiration': [expiration]
                            })
                            
                            if not current_inwork.empty and barcode_clean in current_inwork['Barcode'].values:
                                current_inwork.loc[current_inwork['Barcode'] == barcode_clean, 'Expiration'] = expiration
                                update_inwork(current_inwork)
                                st.success("Срок успешно обновлён!")
                            else:
                                update_inwork(pd.concat([current_inwork, new_row], ignore_index=True))
                                st.success("Товар добавлен в работу!")
                            
                            st.balloons()
                            # Перезапуск страницы для сканирования следующего
                            st.rerun()
            else:
                st.error(f"Штрих-код **{barcode_clean}** не найден в базе.")
                st.markdown("Обнови базу через Excel от офиса и попробуй снова.")
        else:
            st.error("База товаров пуста. Загрузи данные из Excel.")

# Вкладка 3 — Приемка + Печать (оставляем как было, если нужно — доработаем позже)
with tab3:
    st.header("Приемка + Печать")
    st.info("Функционал приёмки и печати этикеток будет добавлен после обхода склада.")

# Вкладка 4 — Просмотр базы
with tab4:
    st.header("Товары в базе")
    products = get_products()
    if not products.empty:
        st.dataframe(products)
    else:
        st.info("База пуста. Загрузи Excel.")

# Вкладка 5 — Настройки цветов
with tab5:
    st.header("Настройки цветов")
    settings = get_settings()
    yellow = st.number_input("Жёлтый цвет: менее месяцев", min_value=1, value=int(settings.get('YellowMonths', 3)))
    red = st.number_input("Красный цвет: менее месяцев", min_value=1, value=int(settings.get('RedMonths', 2)))
    if st.button("Сохранить настройки"):
        update_settings({'YellowMonths': yellow, 'RedMonths': red})
        st.success("Настройки сохранены!")

st.sidebar.info("Версия 1.1 — разработано с помощью Grok")
