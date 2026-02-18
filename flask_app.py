import sqlite3
import os
import telebot
from flask import Flask, render_template, jsonify, request
import threading
from telebot import types # Импортируем типы для создания кнопок

app = Flask(__name__)

# --- НАСТРОЙКИ ---
TOKEN = '8511159340:AAGHwB3RMoyeoNwJ44hrxzwKHWmHkzQfm6Q'
# Ссылка на твой сайт (ОБЯЗАТЕЛЬНО с https и БЕЗ слеша в конце)
URL = 'https://wisposhka.pythonanywhere.com'

bot = telebot.TeleBot(TOKEN, threaded=False)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'school.db')
TOKEN = '8511159340:AAGHwB3RMoyeoNwJ44hrxzwKHWmHkzQfm6Q'
SUPER_ADMIN_ID = 1532505153
CURRENT_SITE_URL = "⏳ Ссылка еще генерируется... Подожди пару секунд."

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- ЛОГИКА БОТА (ВЕБХУК) ---

def init_db():
    conn = sqlite3.connect('DB_PATH')
    c = conn.cursor()
    # Таблица админов (оставляем как было)
    c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (SUPER_ADMIN_ID,))

    # НОВАЯ: Таблица всех пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT
                )''')
    conn.commit()
    conn.close()

init_db() # Запускаем при старте

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    """Сюда Telegram будет присылать сообщения"""
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Бот теперь работает в облаке 24/7! 🚀")

def is_admin(message):
    conn = sqlite3.connect('DB_PATH')
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (message.from_user.id,))
    admin = c.fetchone()
    conn.close()
    return admin is not None

# --- ФУНКЦИИ КЛАВИАТУР ---

def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    btn_link = types.KeyboardButton("🌐 Ссылка на сайт")
    markup.add(btn_link)

    btn1 = types.KeyboardButton("📝 Добавить день")
    btn2 = types.KeyboardButton("📅 Основное расписание")
    btn3 = types.KeyboardButton("🗑 Очистить день")
    btn4 = types.KeyboardButton("💥 Очистить ВСЁ")
    markup.add(btn1, btn2, btn3, btn4)
    if user_id == SUPER_ADMIN_ID:
        markup.add(types.KeyboardButton("👑 Добавить админа"), types.KeyboardButton("👥 Список админов"))
    return markup

def get_days_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "❌ Отмена"]
    btns = [types.KeyboardButton(day) for day in days]
    markup.add(*btns)
    return markup

@bot.message_handler(func=lambda m: m.text == "🌐 Ссылка на сайт")
def send_site_link(message):
    bot.send_message(
        message.chat.id,
        f"📱 **Дневник 8А работает!**\n\nВот актуальная ссылка на сегодня:\n👉 {CURRENT_SITE_URL}",
        parse_mode='Markdown'
    )

# --- ОБРАБОТЧИКИ ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    conn = sqlite3.connect('DB_PATH')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
              (message.from_user.id, message.from_user.username, message.from_user.first_name))
    conn.commit()
    conn.close()
    bot.reply_to(message, "Привет, Админ 8А! Выбери действие:", reply_markup=get_main_keyboard(message.from_user.id))

# --- ПРОСМОТР СТАТИСТИКИ (ТОЛЬКО ДЛЯ СОЗДАТЕЛЯ) ---
@bot.message_handler(commands=['stats'])
def show_statistics(message):
    # Проверка, что спрашиваешь именно ты
    if message.from_user.id != SUPER_ADMIN_ID:
        return

    conn = sqlite3.connect('DB_PATH')
    c = conn.cursor()

    # Считаем общее количество людей в таблице users
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    conn.close()

    text = (
        "📊 **Статистика бота:**\n\n"
        f"👥 Всего учеников запустило бота: **{total_users}**"
    )

    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# 1. Логика ДОБАВЛЕНИЯ ДНЯ (Временные изменения)
@bot.message_handler(func=lambda m: m.text == "📝 Добавить день")
def ask_day_for_add(message):
    if not is_admin(message): return
    msg = bot.send_message(message.chat.id, "На какой день добавляем изменения?", reply_markup=get_days_keyboard())
    bot.register_next_step_handler(msg, process_day_selection, "add")

# 2. Логика ОСНОВНОГО РАСПИСАНИЯ
@bot.message_handler(func=lambda m: m.text == "📅 Основное расписание")
def ask_day_for_main(message):
    if not is_admin(message): return
    msg = bot.send_message(message.chat.id, "Для какого дня задаем ОСНОВНОЕ расписание?", reply_markup=get_days_keyboard())
    bot.register_next_step_handler(msg, process_day_selection, "main")

# 3. Логика ОЧИСТКИ
@bot.message_handler(func=lambda m: m.text == "🗑 Очистить день")
def ask_day_for_clear(message):
    if not is_admin(message): return
    msg = bot.send_message(message.chat.id, "Какой день очистить?", reply_markup=get_days_keyboard())
    bot.register_next_step_handler(msg, process_day_selection, "clear")

# Вспомогательная функция обработки выбора дня
def process_day_selection(message, action):
    day = message.text
    if day == "❌ Отмена":
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))
        return

    if action == "clear":
        execute_clear(message, day)
    else:
        msg = bot.send_message(message.chat.id, f"Пришли расписание на {day} в формате:\n1. Предмет (Каб)\n2. Предмет", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, save_schedule, day, action)

# Сохранение в базу
def save_schedule(message, day, action):
    if not is_admin(message): return

    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))
        return

    lines = message.text.strip().split('\n')
    valid_lines = []
    errors = []
    seen_numbers = set() # Сюда будем складывать номера уроков для проверки на дубли

    for line in lines:
        line = line.strip()
        if not line: continue

        if '.' not in line:
            errors.append(f"В строке '{line}' пропущена точка.")
            continue

        parts = line.split('.', 1)
        num_str = parts[0].strip()
        content = parts[1].strip()

        # 1. Проверяем, что это число
        if not num_str.isdigit():
            errors.append(f"В строке '{line}' номер урока должен быть числом.")
            continue

        lesson_num = int(num_str)

        # 2. ПРОВЕРКА НА ДУБЛИКАТЫ (Новое!)
        if lesson_num in seen_numbers:
            errors.append(f"Номер урока {lesson_num} встречается дважды. Исправь нумерацию.")
            continue

        seen_numbers.add(lesson_num) # Запоминаем номер

        # 3. Проверка названия предмета
        if not content:
            errors.append(f"В строке '{line}' не указано название предмета.")
            continue

        # Парсинг кабинета
        room = "—"
        subject = content
        if '(' in content and ')' in content:
            start, end = content.find('('), content.find(')')
            subject = content[:start].strip()
            room = content[start+1:end].strip()

        valid_lines.append((lesson_num, subject, room))

    # Если есть ошибки — возвращаем на доработку
    if errors:
        error_msg = "❌ **Найдена ошибка в нумерации или формате!**\n\n" + "\n".join(errors)

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Отмена"))

        msg = bot.send_message(message.chat.id, error_msg, reply_markup=markup, parse_mode='Markdown')
        bot.register_next_step_handler(msg, save_schedule, day, action)
        return

    # Сохранение (логика не изменилась)
    table = "lessons" if action == "add" else "main_lessons"
    conn = sqlite3.connect('DB_PATH')
    c = conn.cursor()
    c.execute(f"DELETE FROM {table} WHERE class_name = '8А' AND day = ?", (day,))
    for num, sub, rm in valid_lines:
        c.execute(f"INSERT INTO {table} (day, lesson_num, subject, room, class_name) VALUES (?, ?, ?, ?, '8А')",
                  (day, num, sub, rm))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✅ Расписание на {day} сохранено!", reply_markup=get_main_keyboard(message.from_user.id))

def execute_clear(message, day):
    conn = sqlite3.connect('DB_PATH')
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE class_name = '8А' AND day = ?", (day,))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"🗑 Изменения на {day} удалены.", reply_markup=get_main_keyboard(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "💥 Очистить ВСЁ")
def clear_all(message):
    if not is_admin(message): return
    conn = sqlite3.connect('DB_PATH')
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE class_name = '8А'")
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "💥 Все временные изменения удалены!", reply_markup=get_main_keyboard(message.from_user.id))



# ==========================================
# БЛОК АВТОМАТИЧЕСКОГО СБРОСА РАСПИСАНИЯ
# ==========================================

def auto_clear_schedule():
    """Функция, которая удаляет временное расписание и уведомляет всех админов"""
    try:
        conn = sqlite3.connect('DB_PATH')
        c = conn.cursor()

        # 1. Очищаем расписание
        c.execute("DELETE FROM lessons WHERE class_name = '8А'")

        # 2. Получаем список ID всех администраторов
        c.execute("SELECT user_id FROM admins")
        all_admins = c.fetchall() # Получаем список кортежей, например: [(12345,), (67890,)]

        conn.commit()
        conn.close()

        print("🧹 [АВТООЧИСТКА] Временное расписание сброшено до основного (Понедельник).")

        # 3. Рассылаем уведомление каждому админу
        for admin in all_admins:
            admin_id = admin[0]
            try:
                bot.send_message(admin_id, "🔄 Началась новая неделя! Временные изменения стёрты, включено основное расписание.")
            except Exception as e:
                # Если кто-то из админов заблокировал бота, скрипт не упадет, а просто пойдет дальше
                print(f"Не удалось отправить уведомление админу {admin_id}: {e}")

    except Exception as e:
        print(f"Ошибка при автоочистке: {e}")

# Настраиваем таймер: каждый понедельник ровно в 00:01
schedule.every().monday.at("00:01").do(auto_clear_schedule)

# --- ДОБАВЛЕНИЕ НОВОГО АДМИНА ---

@bot.message_handler(func=lambda m: m.text == "👑 Добавить админа")
def ask_new_admin_id(message):
    # Двойная защита: вдруг кто-то другой попытается отправить этот текст
    if message.from_user.id != SUPER_ADMIN_ID:
        return

    msg = bot.send_message(
        message.chat.id,
        "Пришли мне **Telegram ID** человека, которого хочешь сделать админом.\n\n"
        "*(Чтобы узнать ID, этот человек должен написать боту @getmyid_bot и переслать тебе цифры)*:",
        parse_mode='Markdown',
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("❌ Отмена"))
    )
    bot.register_next_step_handler(msg, process_new_admin)

def process_new_admin(message):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))
        return

    new_admin_id = message.text.strip()

    if not new_admin_id.isdigit():
        msg = bot.send_message(message.chat.id, "❌ Ошибка! ID должен состоять только из цифр. Попробуй еще раз или нажми Отмена:")
        bot.register_next_step_handler(msg, process_new_admin)
        return

    new_admin_id = int(new_admin_id)

    # Сохраняем в базу
    try:
        conn = sqlite3.connect('DB_PATH')
        c = conn.cursor()
        c.execute("INSERT INTO admins (user_id) VALUES (?)", (new_admin_id,))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, f"✅ Супер! Пользователь с ID `{new_admin_id}` назначен администратором. Теперь он тоже может менять расписание.", parse_mode='Markdown', reply_markup=get_main_keyboard(message.from_user.id))

        # Бот может сам поздравить нового админа (если тот уже запускал бота)
        try:
            bot.send_message(new_admin_id, "🎉 Создатель назначил тебя администратором расписания! Нажми /start, чтобы появилось меню управления.")
        except:
            pass # Если бот не может написать (человек еще не запускал бота), просто игнорируем

    except sqlite3.IntegrityError:
        # Если такой ID уже есть в базе
        bot.send_message(message.chat.id, "⚠️ Этот пользователь УЖЕ является администратором.", reply_markup=get_main_keyboard(message.from_user.id))

# --- УПРАВЛЕНИЕ АДМИНАМИ (ПРОСМОТР И УДАЛЕНИЕ) ---

@bot.message_handler(func=lambda m: m.text == "👥 Список админов")
def list_admins(message):
    if message.from_user.id != SUPER_ADMIN_ID:
        return

    conn = sqlite3.connect('DB_PATH')
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins")
    admins = c.fetchall()
    conn.close()

    text = "👥 **Список модераторов:**\n\n"
    for row in admins:
        uid = row[0]
        if uid == SUPER_ADMIN_ID:
            text += f"👑 `{uid}` (Это ты - Создатель)\n"
        else:
            text += f"👤 `{uid}`\n"

    text += "\n❌ Чтобы удалить модератора (забрать права), отправь команду:\n`/del_admin ID`\n*(Например: /del_admin 123456789)*"

    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['del_admin'])
def delete_admin(message):
    if message.from_user.id != SUPER_ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Используй формат: `/del_admin ID`", parse_mode='Markdown')
        return

    target_id = parts[1]
    if not target_id.isdigit():
        bot.reply_to(message, "❌ Ошибка! ID должен состоять только из цифр.")
        return

    target_id = int(target_id)

    # Защита от случайного удаления самого себя
    if target_id == SUPER_ADMIN_ID:
        bot.reply_to(message, "❌ Нельзя удалить самого себя! Ты же Создатель.")
        return

    conn = sqlite3.connect('DB_PATH')
    c = conn.cursor()

    # Проверяем, есть ли такой админ в базе
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (target_id,))
    if not c.fetchone():
        bot.reply_to(message, "🤷‍♂️ Пользователь с таким ID не найден в списке модераторов.")
        conn.close()
        return

    # Удаляем админа
    c.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"✅ Права администратора успешно забраны у пользователя `{target_id}`.", parse_mode='Markdown')

# Фоновый процесс, который проверяет, не наступило ли время

# --- СТРАНИЦЫ САЙТА ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/timetable')
def get_timetable():
    conn = sqlite3.connect('DB_PATH')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    final_schedule = []
    days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница']

    for day in days:
        # 1. Проверяем, есть ли временные изменения на этот день
        c.execute("SELECT * FROM lessons WHERE class_name = '8А' AND day = ? ORDER BY lesson_num", (day,))
        overrides = c.fetchall()

        if overrides:
            # Если нашли изменения, добавляем их
            final_schedule.extend([dict(row) for row in overrides])
        else:
            # 2. Если изменений нет, берем из основного расписания
            c.execute("SELECT * FROM main_lessons WHERE class_name = '8А' AND day = ? ORDER BY lesson_num", (day,))
            main = c.fetchall()
            final_schedule.extend([dict(row) for row in main])

    conn.close()
    return jsonify(final_schedule)

@app.route('/api/main_timetable') # <-- И ЭТУ СТРОКУ
def get_main_timetable():
    conn = sqlite3.connect('DB_PATH')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM main_lessons WHERE class_name = '8А' ORDER BY day, lesson_num")
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

# --- ЗАПУСК ВЕБХУКА ---
@app.route('/set_webhook')
def set_webhook():
    """Эту страницу нужно открыть ОДИН РАЗ в браузере"""
    s = bot.set_webhook(url=f'{URL}/{TOKEN}')
    if s:
        return "Вебхук успешно установлен! Бот готов к работе.", 200
    else:
        return "Ошибка установки вебхука.", 500

if __name__ == '__main__':
    app.run()