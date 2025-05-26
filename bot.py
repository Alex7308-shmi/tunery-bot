import os
import json
import logging
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === НАСТРОЙКИ ===

API_TOKEN = '7573595889:AAGgxZeKwqf2WDsNEF2u3oJsrli84qavn1U'
CHANNEL_USERNAME = "@tunery_mgmt"

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.environ["CREDENTIALS_JSON"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Вопросы. РАБОЧАЯ").sheet1

# Telegram
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# === СОСТОЯНИЯ ===

class Form(StatesGroup):
    category = State()
    question = State()
    anonymity = State()
    answer_format = State()

# === КНОПКИ ===

category_kb = InlineKeyboardMarkup(row_width=2)
category_kb.add(
    InlineKeyboardButton("Релизы", callback_data="cat_Релизы"),
    InlineKeyboardButton("Площадки", callback_data="cat_Площадки"),
    InlineKeyboardButton("Продвижение", callback_data="cat_Продвижение"),
    InlineKeyboardButton("Авторские и смежные права", callback_data="cat_Авторские и смежные права"),
    InlineKeyboardButton("Обложки", callback_data="cat_Обложки"),
    InlineKeyboardButton("Менеджмент", callback_data="cat_Менеджмент"),
    InlineKeyboardButton("Другое", callback_data="cat_Другое"),
)

anon_kb = InlineKeyboardMarkup(row_width=2)
anon_kb.add(
    InlineKeyboardButton("Да", callback_data="anon_Да"),
    InlineKeyboardButton("Нет", callback_data="anon_Нет")
)

format_kb = InlineKeyboardMarkup(row_width=2)
format_kb.add(
    InlineKeyboardButton("Текст", callback_data="format_Текст"),
    InlineKeyboardButton("Голос", callback_data="format_Голос")
)

# === ФУНКЦИИ ===

def generate_upc(sheet):
    existing_upcs = sheet.col_values(6)
    numbers = [int(re.findall(r'\d+', upc)[0]) for upc in existing_upcs if re.match(r"UPC-Q-\d+", upc)]
    next_number = max(numbers) + 1 if numbers else 1
    return f"UPC-Q-{str(next_number).zfill(4)}"

def insert_date_separator(sheet):
    today = datetime.now().strftime('%d.%m.%Y')
    all_dates = sheet.col_values(1)
    if today not in all_dates:
        sheet.append_row([f"=== {today} ==="] + [''] * (sheet.col_count - 1))

# === ХЕНДЛЕРЫ ===

@dp.message_handler(commands='start')
async def start(message: types.Message):
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")
    )
    await message.answer(
        "Привет, это Tunery.bot, где можно задать вопрос о музыкальной индустрии и получить честный ответ от менеджера, который реально в этом работает.\n\n"
        "Здесь мы разбираем:\n"
        "– как устроены релизы\n"
        "– что не так с твоим дропом\n"
        "– как попасть на площадки и не вылететь\n"
        "– и что делать, если всё пошло не так\n"
        "…\n\n"
        "А также любой вопрос касающийся выпуска трека.\n\n"
        "Чтобы продолжить — подпишись на канал @tunery_mgmt, потом нажми кнопку ниже.",
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data == "check_subscription")
async def check_sub(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)

    if member.status in ["member", "administrator", "creator"]:
        await Form.category.set()
        await bot.send_message(user_id, "Спасибо за подписку! Теперь выбери тему вопроса:", reply_markup=category_kb)
    else:
        await bot.send_message(user_id, "Похоже, ты не подписан. Подпишись на @tunery_mgmt и попробуй снова.")

@dp.callback_query_handler(lambda c: c.data.startswith('cat_'), state=Form.category)
async def process_category(callback_query: CallbackQuery, state: FSMContext):
    category = callback_query.data.split('_', 1)[1]
    await state.update_data(category=category)
    await Form.next()
    await bot.send_message(callback_query.from_user.id, f"📝 Тема: *{category}*\n\n✍️ Напиши свой вопрос:", parse_mode="Markdown")

@dp.message_handler(state=Form.question)
async def ask_anonymity(message: types.Message, state: FSMContext):
    await state.update_data(question=message.text)
    await Form.next()
    await message.answer("Показать твой ник в ответе?", reply_markup=anon_kb)

@dp.callback_query_handler(lambda c: c.data.startswith('anon_'), state=Form.anonymity)
async def process_anon(callback_query: CallbackQuery, state: FSMContext):
    anon = callback_query.data.split('_')[1]
    await state.update_data(anonymity=anon)
    await Form.next()
    await bot.send_message(callback_query.from_user.id, "Какой формат ответа хочешь?", reply_markup=format_kb)

@dp.callback_query_handler(lambda c: c.data.startswith('format_'), state=Form.answer_format)
async def process_format(callback_query: CallbackQuery, state: FSMContext):
    fmt = callback_query.data.split('_')[1]
    await state.update_data(answer_format=fmt)

    data = await state.get_data()
    date = datetime.now().strftime('%d.%m.%Y')
    upc = generate_upc(sheet)
    insert_date_separator(sheet)

    sheet.append_row([
        date,
        data['question'],
        data['category'],
        data['anonymity'],
        data['answer_format'],
        upc,
        "Новый",
        str(callback_query.from_user.id),
        ""
    ])

    restart_kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔁 Задать вопрос заново", callback_data="check_subscription")
    )

    await bot.send_message(
        callback_query.from_user.id,
        f"Спасибо! Твой вопрос сохранён. Ответ появится в канале {CHANNEL_USERNAME}",
        reply_markup=restart_kb
    )
    await state.finish()

# === ОБРАБОТКА ОТВЕТА В КАНАЛЕ ===

@dp.channel_post_handler()
async def on_new_channel_post(message: types.Message):
    text = message.text or ""
    match = re.search(r"#UPC-Q-(\d{4})", text)
    
    if match:
        upc_code = f"UPC-Q-{match.group(1)}"
        rows = sheet.get_all_values()

        for i, row in enumerate(rows):
            if len(row) >= 6 and row[5] == upc_code:
                tg_id = row[7] if len(row) >= 8 else None
                if tg_id:
                    link = f"https://t.me/{message.chat.username}/{message.message_id}"
                    sheet.update_cell(i+1, 9, link)
                    try:
                        await bot.send_message(
                            int(tg_id),
                            f"Вопрос на твой ответ по ссылке: {link}"
                        )
                    except Exception as e:
                        print(f"Не удалось отправить сообщение: {e}")

# === ЗАПУСК ===

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
import asyncio
import socket

async def fake_web_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('0.0.0.0', 10000))  # фальшивый порт
    s.listen(1)
    while True:
        await asyncio.sleep(3600)

asyncio.get_event_loop().create_task(fake_web_server())

