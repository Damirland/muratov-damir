import os
import telebot
from flask import Flask, render_template, jsonify, request
from telebot import types
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# --- НАСТРОЙКИ ---
TOKEN = os.getenv('BOT_TOKEN')
DB_URL = os.getenv('DATABASE_URL')
# Убрал слеш в конце URL, чтобы вебхук не ломался (не //8511...)
URL = 'https://eighta-diary.onrender.com' 
SUPER_ADMIN_ID = 1532505153
CURRENT_SITE_URL = URL

bot = telebot.TeleBot(TOKEN, threaded=False)

def get_db_connection():
    # Подключаемся к Supabase через psycopg2
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Создаем таблицы (в Postgres синтаксис такой же)
    c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id BIGINT PRIMARY KEY)''')
    # ВАЖНО: Вместо ? используем %s
    c.execute("INSERT INTO admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (SUPER_ADMIN_ID,))
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, 
                    username TEXT, 
                    first_name TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS lessons 
                 (id SERIAL PRIMARY KEY, class_name TEXT, day TEXT, lesson_num INTEGER, subject TEXT, room TEXT)''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS main_lessons 
                 (id SERIAL PRIMARY KEY, class_name TEXT, day TEXT, lesson_num INTEGER, subject TEXT, room TEXT)''')
    
    conn.commit()
    c.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"Ошибка инициализации БД: {e}")

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    """Сюда Telegram будет присылать сообщения"""
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

def is_admin(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = %s", (user_id,))
    admin = c.fetchone()
    c.close()
    conn.close()
    return admin is not None

# --- ФУНКЦИИ КЛАВИАТУР ---
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_link = types.KeyboardButton("🌐 Ссылка на сайт")
    markup.add(btn_link)

    if is_admin(user_id):
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

# --- ОБРАБОТЧИКИ ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    conn = get_db_connection()
    c = conn.cursor()
    # В PostgreSQL используется ON CONFLICT вместо OR IGNORE
    c.execute("INSERT INTO users (user_id, username, first_name) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
              (message.from_user.id, message.from_user.username, message.from_user.first_name))
    conn.commit()
    c.close()
    conn.close()
    bot.reply_to(message, "Привет! Выбери действие:", reply_markup=get_main_keyboard(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🌐 Ссылка на сайт")
def send_site_link(message):
    bot.send_message(
        message.chat.id,
        f"📱 **Дневник 8А работает!**\n\nВот актуальная ссылка:\n👉 {CURRENT_SITE_URL}",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['stats'])
def show_statistics(message):
    if message.from_user.id != SUPER_ADMIN_ID: return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.close()
    conn.close()
    text = f"📊 **Статистика бота:**\n\n👥 Всего учеников запустило бота: **{total_users}**"
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# 1. Логика ДОБАВЛЕНИЯ ДНЯ
@bot.message_handler(func=lambda m: m.text == "📝 Добавить день")
def ask_day_for_add(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "На какой день добавляем изменения?", reply_markup=get_days_keyboard())
    bot.register_next_step_handler(msg, process_day_selection, "add")

# 2. Логика ОСНОВНОГО РАСПИСАНИЯ
@bot.message_handler(func=lambda m: m.text == "📅 Основное расписание")
def ask_day_for_main(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "Для какого дня задаем ОСНОВНОЕ расписание?", reply_markup=get_days_keyboard())
    bot.register_next_step_handler(msg, process_day_selection, "main")

# 3. Логика ОЧИСТКИ
@bot.message_handler(func=lambda m: m.text == "🗑 Очистить день")
def ask_day_for_clear(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "Какой день очистить?", reply_markup=get_days_keyboard())
    bot.register_next_step_handler(msg, process_day_selection, "clear")

def process_day_selection(message, action):
    day = message.text
    if day == "❌ Отмена":
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))
        return

    if action == "clear":
        execute_clear(message, day)
    else:
        msg = bot.send_message(message.chat.id, f"Пришли расписание на {day} в формате:\n1. Предмет (Каб)", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, save_schedule, day, action)

def save_schedule(message, day, action):
    if not is_admin(message.from_user.id): return
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))
        return

    lines = message.text.strip().split('\n')
    valid_lines = []
    errors = []
    seen_numbers = set()

    for line in lines:
        line = line.strip()
        if not line: continue
        if '.' not in line:
            errors.append(f"В строке '{line}' пропущена точка.")
            continue
        parts = line.split('.', 1)
        num_str = parts[0].strip()
        content = parts[1].strip()

        if not num_str.isdigit():
            errors.append(f"В строке '{line}' номер урока должен быть числом.")
            continue
        lesson_num = int(num_str)

        if lesson_num in seen_numbers:
            errors.append(f"Номер урока {lesson_num} встречается дважды. Исправь нумерацию.")
            continue
        seen_numbers.add(lesson_num)

        if not content:
            errors.append(f"В строке '{line}' не указано название предмета.")
            continue

        room, subject = "—", content
        if '(' in content and ')' in content:
            start, end = content.find('('), content.find(')')
            subject = content[:start].strip()
            room = content[start+1:end].strip()
        valid_lines.append((lesson_num, subject, room))

    if errors:
        error_msg = "❌ **Найдена ошибка в нумерации или формате!**\n\n" + "\n".join(errors) + "\n\nИсправь и пришли заново:"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("❌ Отмена"))
        msg = bot.send_message(message.chat.id, error_msg, reply_markup=markup, parse_mode='Markdown')
        bot.register_next_step_handler(msg, save_schedule, day, action)
        return

    table = "lessons" if action == "add" else "main_lessons"
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(f"DELETE FROM {table} WHERE class_name = '8А' AND day = %s", (day,))
    for num, sub, rm in valid_lines:
        c.execute(f"INSERT INTO {table} (day, lesson_num, subject, room, class_name) VALUES (%s, %s, %s, %s, '8А')",
                  (day, num, sub, rm))
    conn.commit()
    c.close()
    conn.close()
    bot.send_message(message.chat.id, f"✅ Расписание на {day} сохранено!", reply_markup=get_main_keyboard(message.from_user.id))

def execute_clear(message, day):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE class_name = '8А' AND day = %s", (day,))
    conn.commit()
    c.close()
    conn.close()
    bot.send_message(message.chat.id, f"🗑 Изменения на {day} удалены.", reply_markup=get_main_keyboard(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "💥 Очистить ВСЁ")
def clear_all(message):
    if not is_admin(message.from_user.id): return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE class_name = '8А'")
    conn.commit()
    c.close()
    conn.close()
    bot.send_message(message.chat.id, "💥 Все временные изменения удалены!", reply_markup=get_main_keyboard(message.from_user.id))

def auto_clear_schedule():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM lessons WHERE class_name = '8А'")
        c.execute("SELECT user_id FROM admins")
        all_admins = c.fetchall()
        conn.commit()
        c.close()
        conn.close()

        print("🧹 [АВТООЧИСТКА] Сброшено до основного расписания.")
        for admin in all_admins:
            admin_id = admin[0]
            try:
                bot.send_message(admin_id, "🔄 Временные изменения стёрты, включено основное расписание.")
            except:
                pass
    except Exception as e:
        print(f"Ошибка при автоочистке: {e}")

# --- ДОБАВЛЕНИЕ НОВОГО АДМИНА ---
@bot.message_handler(func=lambda m: m.text == "👑 Добавить админа")
def ask_new_admin_id(message):
    if message.from_user.id != SUPER_ADMIN_ID: return
    msg = bot.send_message(
        message.chat.id,
        "Пришли мне **Telegram ID** нового админа:",
        parse_mode='Markdown',
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("❌ Отмена"))
    )
    bot.register_next_step_handler(msg, process_new_admin)

def process_new_admin(message):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))
        return
    if not message.text.isdigit():
        msg = bot.send_message(message.chat.id, "❌ Ошибка! ID должен состоять только из цифр. Попробуй еще раз:")
        bot.register_next_step_handler(msg, process_new_admin)
        return

    new_admin_id = int(message.text.strip())
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO admins (user_id) VALUES (%s)", (new_admin_id,))
        conn.commit()
        c.close()
        conn.close()
        bot.send_message(message.chat.id, f"✅ Пользователь `{new_admin_id}` назначен администратором.", parse_mode='Markdown', reply_markup=get_main_keyboard(message.from_user.id))
        try:
            bot.send_message(new_admin_id, "🎉 Создатель назначил тебя администратором! Нажми /start.")
        except: pass
    except psycopg2.IntegrityError:
        bot.send_message(message.chat.id, "⚠️ Этот пользователь УЖЕ администратор.", reply_markup=get_main_keyboard(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "👥 Список админов")
def list_admins(message):
    if message.from_user.id != SUPER_ADMIN_ID: return
    conn = get_db_connection()
    c = conn.cursor()
    query = """
        SELECT a.user_id, u.username, u.first_name 
        FROM admins a
        LEFT JOIN users u ON a.user_id = u.user_id
    """
    c.execute(query)
    admins = c.fetchall()
    c.close()
    conn.close()

    text = "👥 **Список модераторов:**\n\n"
    for row in admins:
        uid, username, first_name = row
        if username: display_name = f"@{username}"
        elif first_name: display_name = f"{first_name} (ID: {uid})"
        else: display_name = f"ID: {uid}"
            
        if uid == SUPER_ADMIN_ID: text += f"👑 {display_name} (Создатель)\n"
        else: text += f"👤 {display_name}\n"

    text += "\n❌ Чтобы удалить модератора, отправь:\n`/del_admin ID`"
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['del_admin'])
def delete_admin(message):
    if message.from_user.id != SUPER_ADMIN_ID: return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "⚠️ Формат: `/del_admin ID`", parse_mode='Markdown')
        return

    target_id = int(parts[1])
    if target_id == SUPER_ADMIN_ID:
        bot.reply_to(message, "❌ Нельзя удалить самого себя!")
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = %s", (target_id,))
    if not c.fetchone():
        bot.reply_to(message, "🤷‍♂️ Пользователь не найден.")
        c.close()
        conn.close()
        return

    c.execute("DELETE FROM admins WHERE user_id = %s", (target_id,))
    conn.commit()
    c.close()
    conn.close()
    bot.reply_to(message, f"✅ Права администратора забраны у `{target_id}`.", parse_mode='Markdown')

# --- СТРАНИЦЫ САЙТА ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/main')
def main_page():
    return render_template('main.html')

@app.route('/api/timetable')
def get_timetable():
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=RealDictCursor) # Возвращает готовые словари для JSON

    final_schedule = []
    days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница']

    for day in days:
        c.execute("SELECT * FROM lessons WHERE class_name = '8А' AND day = %s ORDER BY lesson_num", (day,))
        overrides = c.fetchall()

        if overrides:
            final_schedule.extend(overrides)
        else:
            c.execute("SELECT * FROM main_lessons WHERE class_name = '8А' AND day = %s ORDER BY lesson_num", (day,))
            main = c.fetchall()
            final_schedule.extend(main)

    c.close()
    conn.close()
    return jsonify(final_schedule)

@app.route('/api/main_timetable')
def get_main_timetable():
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("SELECT * FROM main_lessons WHERE class_name = '8А' ORDER BY day, lesson_num")
    rows = c.fetchall()
    c.close()
    conn.close()
    return jsonify(rows)

# --- ЗАПУСК ВЕБХУКА ---
@app.route('/set_webhook')
def set_webhook():
    """Эту страницу нужно открыть ОДИН РАЗ в браузере"""
    bot.remove_webhook()
    s = bot.set_webhook(url=f'{URL}/{TOKEN}')
    if s:
        return "Вебхук успешно установлен! Бот готов к работе.", 200
    else:
        return "Ошибка установки вебхука.", 500

if __name__ == '__main__':
    # На Render порт задается через переменную окружения (по умолчанию 5000)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
