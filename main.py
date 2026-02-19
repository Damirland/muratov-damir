import os
import telebot
from flask import Flask, render_template, jsonify, request
from telebot import types
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import requests
import uuid
load_dotenv()

app = Flask(__name__)

# --- НАСТРОЙКИ ---
TOKEN = os.getenv('BOT_TOKEN')
DB_URL = os.getenv('DATABASE_URL')
# Убрал слеш в конце URL, чтобы вебхук не ломался (не //8511...)
URL = 'https://muratov-damir.onrender.com' 
SUPER_ADMIN_ID = 1532505153
CURRENT_SITE_URL = URL
CRON_SECRET = os.getenv('CRON_SECRET', 'super-secret-reset-8a')

bot = telebot.TeleBot(TOKEN, threaded=False)

# --- ДЕФОЛТНЫЕ КАБИНЕТЫ ДЛЯ ПРЕДМЕТОВ ---
DEFAULT_ROOMS = {
    'Алгебра': '404', 
    'Геометрия': '404',
    'Вероятность и статистика': '404', 
    'Дополнительная математика': '404',
    'Математика(доп)': '404',
    'математика(доп)': '404',
    'Решение задач по математике': '404',

    'Русский язык': '401', 
    'Литература': '401',
    'Практикум по русскому языку': '401', 
    'Функциональная грамотность': '418',

    'Английский язык': '403 / 103', 
    'Английский язык / Информатика': '102 / 318',

    'Информатика': '318', 
    'Дополнительная информатика': '312',
    'Информатика(доп)': '312',

    'Физика': '204', 
    'Химия': '302', 
    'Биология': '304',
    'География': '409',

    'История': '413', 
    'Обществознание': '116', 
    'Семьеведение': '401',
    'ОБЗР': '—', 
    'Основы безопасности и защиты Родины': '—',

    'Физкультура': 'зал №1', 
    'Физическая культура': 'зал №1', 
    'Музыка': '102', 
    'Труд': '201',
    'Труд(технология)': '201',
    'Классный час': '401',
    'Разговор о важном': '401',
    'Россия - мои горизонты': '401',
    'Россия — мои горизонты': '401'
}

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
    
    # === ТАБЛИЦА ДЛЯ ДОМАШКИ ===
    c.execute('''CREATE TABLE IF NOT EXISTS homework 
                 (id SERIAL PRIMARY KEY, day TEXT, subject TEXT, task TEXT, UNIQUE(day, subject))''')
                 
    # Добавляем колонку для фото, если ее еще нет
    c.execute("ALTER TABLE homework ADD COLUMN IF NOT EXISTS photo_url TEXT")
    
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
        btn1 = types.KeyboardButton("📝 Добавить изменение")
        btn2 = types.KeyboardButton("📅 Изменить основное расписание")
        btn3 = types.KeyboardButton("🗑 Очистить изменения дня")
        btn4 = types.KeyboardButton("💥 Сбросить все до основного расписания")
        btn5 = types.KeyboardButton("📚 Управление домашкой") # Новая кнопка
        markup.add(btn1, btn2, btn3, btn4, btn5)
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
@bot.message_handler(func=lambda m: m.text == "📝 Добавить изменение")
def ask_day_for_add(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "На какой день добавляем изменения?", reply_markup=get_days_keyboard())
    bot.register_next_step_handler(msg, process_day_selection, "add")

# 2. Логика ОСНОВНОГО РАСПИСАНИЯ
@bot.message_handler(func=lambda m: m.text == "📅 Изменить основное расписание")
def ask_day_for_main(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "Для какого дня задаем ОСНОВНОЕ расписание?", reply_markup=get_days_keyboard())
    bot.register_next_step_handler(msg, process_day_selection, "main")

# 3. Логика ОЧИСТКИ
@bot.message_handler(func=lambda m: m.text == "🗑 Очистить изменения дня")
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
        try:
            # Подключаемся к базе, чтобы достать текущее расписание
            conn = get_db_connection()
            c = conn.cursor()
            current_lessons = []
            
            if action == "add":
                c.execute("SELECT lesson_num, subject, room FROM lessons WHERE class_name = '8А' AND day = %s ORDER BY lesson_num", (day,))
                current_lessons = c.fetchall()
                
            if not current_lessons:
                c.execute("SELECT lesson_num, subject, room FROM main_lessons WHERE class_name = '8А' AND day = %s ORDER BY lesson_num", (day,))
                current_lessons = c.fetchall()
                
            c.close()
            conn.close()

            if current_lessons:
                schedule_text = "\n".join([f"{row[0]}. {row[1]} ({row[2]})" for row in current_lessons])
            else:
                schedule_text = "1. Предмет (Каб)\n2. Предмет (Каб)"

            # Убрали Markdown (обратные кавычки), чтобы избежать сбоев при копировании
            msg_text = f"Пришли расписание на {day.lower()} в формате ниже (кабинет вставляется автоматически, но если надо указать другой, то указываем в скобочках):\n\n{schedule_text}"
            
            # Создаем клавиатуру только с одной кнопкой Отмена
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("❌ Отмена"))
            msg = bot.send_message(message.chat.id, msg_text, reply_markup=markup)
            bot.register_next_step_handler(msg, save_schedule, day, action)
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠️ Ошибка при загрузке шаблона: {e}")

def save_schedule(message, day, action):
    try:
        if not is_admin(message.from_user.id): return
        
        # Защита от отправки фото/стикера вместо текста
        if not message.text:
            msg = bot.send_message(message.chat.id, "❌ Пожалуйста, отправь расписание текстом.")
            bot.register_next_step_handler(msg, save_schedule, day, action)
            return

        if message.text == "❌ Отмена":
            bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))
            return

        lines = message.text.strip().split('\n')
        valid_lines = []
        errors = []
        seen_numbers = set()

        for line in lines:
            line = line.strip()
            line = line.replace('`', '') # Очищаем от случайных кавычек
            
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

            # --- НОВАЯ ЛОГИКА КАБИНЕТОВ С ПРАВИЛЬНЫМИ ОТСТУПАМИ ---
            if '(' in content and ')' in content:
                start, end = content.find('('), content.rfind(')')
                subject = content[:start].strip()
                room = content[start+1:end].strip()
            else:
                subject = content.strip()
                room = DEFAULT_ROOMS.get(subject, "—")
                
            valid_lines.append((lesson_num, subject, room))

        if errors:
            error_msg = "❌ Найдена ошибка в нумерации или формате!\n\n" + "\n".join(errors) + "\n\nИсправь и пришли заново:"
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("❌ Отмена"))
            msg = bot.send_message(message.chat.id, error_msg, reply_markup=markup)
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
        
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Системная ошибка при сохранении:\n{e}\n\nПопробуйте еще раз.", reply_markup=get_main_keyboard(message.from_user.id))

def execute_clear(message, day):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE class_name = '8А' AND day = %s", (day,))
    conn.commit()
    c.close()
    conn.close()
    bot.send_message(message.chat.id, f"🗑 Изменения на {day} удалены.", reply_markup=get_main_keyboard(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "💥 Сбросить все до основного расписания")
def clear_all(message):
    if not is_admin(message.from_user.id): return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE class_name = '8А'")
    c.execute("DELETE FROM homework")
    conn.commit()
    c.close()
    conn.close()
    bot.send_message(message.chat.id, "💥 Все временные изменения удалены!", reply_markup=get_main_keyboard(message.from_user.id))

def auto_clear_schedule():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM lessons WHERE class_name = '8А'")
        c.execute("DELETE FROM homework")
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

# --- ЛОГИКА ДОМАШНИХ ЗАДАНИЙ ---
@bot.message_handler(func=lambda m: m.text == "📚 Управление домашкой")
def ask_hw_day(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "На какой день задаем домашку?", reply_markup=get_days_keyboard())
    bot.register_next_step_handler(msg, process_hw_day)

def process_hw_day(message):
    day = message.text
    if day == "❌ Отмена":
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))
        return

    # Достаем расписание на этот день для подсказки
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT lesson_num, subject FROM lessons WHERE class_name='8А' AND day=%s ORDER BY lesson_num", (day,))
    subs = c.fetchall()
    if not subs: # Если временных нет, берем из основного
        c.execute("SELECT lesson_num, subject FROM main_lessons WHERE class_name='8А' AND day=%s ORDER BY lesson_num", (day,))
        subs = c.fetchall()
    c.close()
    conn.close()

    if not subs:
        bot.send_message(message.chat.id, f"На {day} нет уроков в базе!", reply_markup=get_main_keyboard(message.from_user.id))
        return

    # Формируем красивый список уроков
    schedule_text = "\n".join([f"{row[0]}. {row[1]}" for row in subs])
    
    instructions = (
        f"📅 **Расписание на {day}:**\n{schedule_text}\n\n"
        f"Напиши домашнее задание **ОДНИМ сообщением**.\n"
        f"📸 **Ты можешь прикрепить ОДНО фото к этому сообщению!** (Текст пиши прямо в подписи к фото).\n\n"
        f"`Алгебра: номера 123`\n"
        f"`Химия: параграф 5`\n\n"
        f"*(Чтобы удалить домашку, напиши `Предмет: -`)*"
    )

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("❌ Отмена"))
    msg = bot.send_message(message.chat.id, instructions, parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(msg, save_multiple_hw, day)

def save_multiple_hw(message, day):
    # Если прислали картинку, текст будет в caption. Иначе в text.
    text = message.caption if message.photo else message.text

    if not text:
        msg = bot.send_message(message.chat.id, "❌ Я не вижу текста. Пожалуйста, отправь текст или прикрепи фото **с подписью**.")
        bot.register_next_step_handler(msg, save_multiple_hw, day)
        return

    if text == "❌ Отмена":
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_keyboard(message.fromuser.id))
        return

    # --- ЗАГРУЗКА ФОТО В ОБЛАКО ---
    photo_public_url = None
    if message.photo:
        try:
            bot.send_message(message.chat.id, "⏳ Обрабатываю фото и загружаю в облако...")
            
            # Берем фото в максимальном качестве
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Уникальное имя для файла
            file_name = f"{uuid.uuid4()}.jpg"
            
            supabase_url = os.getenv('SUPABASE_URL', '').rstrip('/')
            supabase_key = os.getenv('SUPABASE_KEY')
            
            # API запрос к Supabase Storage
            upload_url = f"{supabase_url}/storage/v1/object/homework/{file_name}"
            headers = {
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key,
                "Content-Type": "image/jpeg"
            }
            
            resp = requests.post(upload_url, headers=headers, data=downloaded_file)
            
            if resp.status_code == 200:
                photo_public_url = f"{supabase_url}/storage/v1/object/public/homework/{file_name}"
            else:
                bot.send_message(message.chat.id, f"⚠️ Не удалось сохранить фото в облако. Будет сохранен только текст.")
        except Exception as e:
            print(f"Ошибка загрузки фото: {e}")
            bot.send_message(message.chat.id, "⚠️ Произошла ошибка при загрузке фото.")

    lines = text.strip().split('\n')
    saved_count = 0
    errors = []
    moved_info = []

    full_week = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница']
    conn = get_db_connection()
    c = conn.cursor()

    # --- СОБИРАЕМ АКТУАЛЬНОЕ РАСПИСАНИЕ ---
    c.execute("SELECT day, subject FROM lessons WHERE class_name='8А'")
    temp_lessons = c.fetchall()
    c.execute("SELECT day, subject FROM main_lessons WHERE class_name='8А'")
    main_lessons = c.fetchall()

    schedule = {d: set() for d in full_week}
    for d, s in main_lessons:
        if d in schedule: schedule[d].add(s.strip().lower())

    days_with_temp = set([r[0] for r in temp_lessons])
    for d in days_with_temp:
        if d in schedule: schedule[d] = set()

    for d, s in temp_lessons:
        if d in schedule: schedule[d].add(s.strip().lower())

    # --- ОБРАБАТЫВАЕМ ТЕКСТ ---
    for line in lines:
        line = line.strip()
        if not line: continue
        
        if ':' not in line:
            errors.append(f"Пропущено (нет двоеточия): `{line}`")
            continue

        parts = line.split(':', 1)
        original_subject = parts[0].strip()
        task = parts[1].strip()

        if task.startswith('"') and task.endswith('"'): task = task[1:-1].strip()
        elif task.startswith("'") and task.endswith("'"): task = task[1:-1].strip()

        if not original_subject or not task:
            errors.append(f"Пропущено (пустое значение): `{line}`")
            continue

        norm_sub = original_subject.lower()
        target_day = day
        
        # --- УМНЫЙ ПЕРЕНОС ---
        if day in full_week:
            start_index = full_week.index(day)
            if norm_sub not in schedule[target_day]:
                found = False
                for i in range(start_index, len(full_week)):
                    if norm_sub in schedule[full_week[i]]:
                        target_day = full_week[i]
                        found = True
                        break
                if not found:
                    for i in range(0, start_index):
                        if norm_sub in schedule[full_week[i]]:
                            target_day = full_week[i]
                            break
                if target_day != day and task != '-' and task != '—':
                    moved_info.append(f"🔄 **{original_subject}** перенесен(а) на **{target_day}**")

        # --- СОХРАНЯЕМ В БАЗУ (ТЕПЕРЬ С ФОТО) ---
        if task == '-' or task == '—':
            c.execute("DELETE FROM homework WHERE day=%s AND subject=%s", (target_day, original_subject))
            c.execute("DELETE FROM homework WHERE day=%s AND subject=%s", (day, original_subject))
            c.execute("SELECT day FROM homework WHERE subject=%s", (original_subject,))
            for (hw_day,) in c.fetchall():
                if norm_sub not in schedule.get(hw_day, set()):
                    c.execute("DELETE FROM homework WHERE day=%s AND subject=%s", (hw_day, original_subject))
            saved_count += 1
        else:
            c.execute("""INSERT INTO homework (day, subject, task, photo_url) VALUES (%s, %s, %s, %s) 
                         ON CONFLICT (day, subject) DO UPDATE SET task = EXCLUDED.task, photo_url = EXCLUDED.photo_url""", 
                      (target_day, original_subject, task, photo_public_url))
            saved_count += 1

    conn.commit()
    c.close()
    conn.close()

    response = f"✅ Успешно обработано заданий: **{saved_count}**."
    if moved_info: response += "\n\n" + "\n".join(moved_info)
    if errors: response += "\n\n⚠️ **Ошибки:**\n" + "\n".join(errors)

    bot.send_message(message.chat.id, response, parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

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
        
        # Добавляем ID ко всем вариантам отображения (и делаем его копируемым ` `)
        if username: 
            display_name = f"@{username} (ID: `{uid}`)"
        elif first_name: 
            display_name = f"{first_name} (ID: `{uid}`)"
        else: 
            display_name = f"ID: `{uid}`"
            
        if uid == SUPER_ADMIN_ID: 
            text += f"👑 {display_name} (Создатель)\n"
        else: 
            text += f"👤 {display_name}\n"

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

@app.route('/api/reset_schedule/' + CRON_SECRET)
def web_clear_schedule():
    """Секретная ссылка для автоматического сброса расписания"""
    try:
        # У тебя уже есть крутая функция auto_clear_schedule, 
        # которая не только чистит базу, но и рассылает уведомления админам. 
        # Просто вызываем её!
        auto_clear_schedule()
        return "✅ Временное расписание успешно сброшено!", 200
    except Exception as e:
        return f"❌ Ошибка при сбросе: {e}", 500

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

@app.route('/homework')
def homework_page():
    return render_template('homework.html')

@app.route('/api/homework')
def get_homework_api():
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("SELECT * FROM homework")
    hw = c.fetchall()
    c.close()
    conn.close()
    return jsonify(hw)

if __name__ == '__main__':
    # На Render порт задается через переменную окружения (по умолчанию 5000)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
