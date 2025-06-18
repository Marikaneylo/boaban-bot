import os
import json
import time
import threading
import ssl
from datetime import datetime, timedelta
from typing import Dict
from flask import Flask, request, jsonify
import urllib.request
import urllib.parse
import sqlite3
import schedule
import random

# Flask приложение
app = Flask(__name__)

# Игнорируем SSL сертификаты (для macOS)
ssl._create_default_https_context = ssl._create_unverified_context

# Токен бота из переменных окружения (ВАЖНО!)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# URL вашего приложения - получаем из переменных окружения
APP_NAME = os.environ.get("APP_NAME", "baoban")
WEBHOOK_URL = f"https://{APP_NAME}.osc-fr1.scalingo.io/webhook"

# Инициализация базы данных
def init_db():
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                sleep_hour INTEGER,
                sleep_minute INTEGER,
                notifications_active BOOLEAN DEFAULT 0,
                last_notification TEXT
            )
        ''')
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")

# Агрессивные сообщения с разной степенью агрессивности
AGGRESSIVE_MESSAGES = {
    60: [
        "🔥 Час до сна! Время действовать, а не листать ленту как зомби!",
        "⏰ 60 минут до сна! Твоя подушка уже скучает по тебе больше, чем ты по успеху",
        "🎯 Час до отбоя! Пора заканчивать с этим цирком и идти спать",
        "💀 60 минут! Твоя бессонница не сделает тебя гением, поверь мне",
        "🚨 Остался час! Твой завтрашний день уже плачет от твоих сегодняшних решений"
    ],
    30: [
        "⚡ Полчаса! Хватит откладывать, твоя прокрастинация уже легендарна!",
        "🔥 30 минут до сна! Твой организм ненавидит тебя больше, чем понедельники",
        "💀 Полчаса осталось! Ты же не хочешь завтра выглядеть как зомби из фильма ужасов?",
        "⏰ 30 минут! Время тикает быстрее твоих оправданий",
        "🚨 Полчаса до сна! Red alert! Твоя кровать объявляет ультиматум"
    ],
    20: [
        "💀 20 минут! Время критично, как твоя ситуация с режимом сна!",
        "🚨 20 минут до сна! Красная зона! Твоя кровать вызывает подкрепление",
        "⚡ 20 минут! Молния должна бы уже ударить в твою голову",
        "🔥 20 минут до сна! Пожарная тревога! Горит твой завтрашний день",
        "💣 20 минут! Взрывоопасная ситуация с твоим расписанием"
    ],
    10: [
        "🚨 10 минут! Последний шанс! Твоя кровать подает на развод!",
        "💀 10 минут до сна! Смертельная доза упрямства превышена",
        "⚡ 10 минут! Молния кармы ударит завтра с утра",
        "🔥 10 минут до сна! Пожар в мозгах завтра будет эпическим",
        "💣 10 минут! Ядерная боеголовка усталости на подлете"
    ],
    5: [
        "🔥 5 минут! Критическое время! Твоя кровать вызывает экстренные службы!",
        "💀 5 минут до сна! Агония здравого смысла! Пора в реанимацию!",
        "⚡ 5 минут! Электрошок завтра будет бесплатным!",
        "🚨 5 минут до сна! Красный код! Всем покинуть зону бедствия!",
        "💣 5 минут! Детонация глупости через 5... 4... 3..."
    ],
    0: [
        "⏰ ВРЕМЯ ПРИШЛО! Немедленно спать! Твоя кровать объявляет войну!",
        "💀 ПОРА СПАТЬ! Смерть продуктивности наступила! R.I.P. завтрашний день!",
        "🔥 ВРЕМЯ СНА! Пожар в мозгах завтра будет эпических масштабов!",
        "⚡ СПАТЬ НЕМЕДЛЕННО! Электричество в мозгу будет отключено!",
        "🚨 ВРЕМЯ ПРИШЛО! Красная тревога! Все системы отказали!"
    ]
}

def make_request(url, data=None, method='GET'):
    """Делает HTTP запрос с обработкой ошибок"""
    try:
        if method == 'POST' and data:
            data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=data)
            req.add_header('Content-Type', 'application/json')
        else:
            if data:
                url += '?' + urllib.parse.urlencode(data)
            req = urllib.request.Request(url)

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
            if not result.get('ok', False):
                print(f"❌ Telegram API error: {result.get('description', 'Unknown error')}")
            return result
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None

def send_message(chat_id, text, reply_markup=None):
    """Отправляет сообщение пользователю"""
    url = BASE_URL + "sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup:
        data["reply_markup"] = reply_markup

    result = make_request(url, data, 'POST')
    if result and result.get('ok'):
        print(f"✅ Сообщение отправлено пользователю {chat_id}")
    else:
        print(f"❌ Ошибка отправки сообщения пользователю {chat_id}")
    return result

def get_sleep_button():
    """Создает кнопку 'Ложусь спать'"""
    return {
        "inline_keyboard": [[
            {
                "text": "😴 Ложусь спать",
                "callback_data": "going_to_sleep"
            }
        ]]
    }

def save_user_data(chat_id, sleep_hour, sleep_minute, notifications_active=True):
    """Сохраняет данные пользователя в БД"""
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (chat_id, sleep_hour, sleep_minute, notifications_active)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, sleep_hour, sleep_minute, notifications_active))
        conn.commit()
        conn.close()
        print(f"✅ Данные пользователя {chat_id} сохранены")
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")

def get_user_data(chat_id):
    """Получает данные пользователя из БД"""
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE chat_id = ?', (chat_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        print(f"❌ Ошибка получения данных: {e}")
        return None

def update_user_notifications(chat_id, active):
    """Обновляет статус уведомлений пользователя"""
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET notifications_active = ? WHERE chat_id = ?
        ''', (active, chat_id))
        conn.commit()
        conn.close()
        print(f"✅ Уведомления пользователя {chat_id} {'включены' if active else 'отключены'}")
    except Exception as e:
        print(f"❌ Ошибка обновления уведомлений: {e}")

def check_and_send_notifications():
    """Проверяет и отправляет уведомления"""
    try:
        current_time = datetime.now()
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # Получаем всех активных пользователей
        cursor.execute('''
            SELECT chat_id, sleep_hour, sleep_minute FROM users 
            WHERE notifications_active = 1
        ''')
        
        users = cursor.fetchall()
        conn.close()
        
        for chat_id, sleep_hour, sleep_minute in users:
            # Создаем время сна для сегодня
            sleep_time = current_time.replace(hour=sleep_hour, minute=sleep_minute, second=0, microsecond=0)
            
            # Если время сна уже прошло, берем завтрашний день
            if sleep_time < current_time:
                sleep_time += timedelta(days=1)
            
            # Вычисляем разницу до времени сна
            time_diff = sleep_time - current_time
            minutes_left = int(time_diff.total_seconds() / 60)
            
            # Отправляем уведомления в нужные моменты
            if minutes_left in [60, 30, 20, 10, 5, 0] and time_diff.total_seconds() < 60:
                message = random.choice(AGGRESSIVE_MESSAGES[minutes_left])
                send_message(chat_id, message, get_sleep_button())
                print(f"✅ Отправлено уведомление за {minutes_left} минут пользователю {chat_id}")
                
    except Exception as e:
        print(f"❌ Ошибка проверки уведомлений: {e}")

def run_scheduler():
    """Запускает планировщик уведомлений"""
    print("🔄 Планировщик запущен")
    while True:
        try:
            check_and_send_notifications()
            time.sleep(30)  # Проверяем каждые 30 секунд
        except Exception as e:
            print(f"❌ Ошибка в планировщике: {e}")
            time.sleep(60)

# Webhook endpoint
@app.route('/webhook', methods=['POST'])
def webhook():
    """Обрабатывает входящие сообщения от Telegram"""
    try:
        update = request.get_json()
        print(f"📨 Получено обновление: {update}")
        
        if "message" in update:
            handle_message(update["message"])
        elif "callback_query" in update:
            handle_callback_query(update["callback_query"])
            
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/', methods=['GET'])
def home():
    """Главная страница"""
    return jsonify({
        "status": "running", 
        "bot": "Sleep Reminder Bot",
        "webhook_url": WEBHOOK_URL
    })

def handle_message(message):
    """Обрабатывает текстовые сообщения"""
    try:
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        print(f"📝 Сообщение от {chat_id}: {text}")

        if text == "/start":
            send_message(chat_id,
                         "🌙 Добро пожаловать в бот агрессивных напоминаний о сне!\n\n"
                         "Этот бот будет ЖЕСТКО напоминать тебе о времени сна.\n"
                         "Никакой мотивации, только суровая правда!\n\n"
                         "Используй /setsleep чтобы установить время сна\n"
                         "Используй /cancel чтобы отменить напоминания\n"
                         "Используй /status чтобы проверить настройки")

        elif text == "/setsleep":
            send_message(chat_id,
                         "⏰ Введи время сна в формате ЧЧ:ММ (например: 23:00 или 21:30)\n"
                         "После этого я буду агрессивно напоминать тебе ложиться спать!")

        elif text == "/cancel":
            update_user_notifications(chat_id, False)
            send_message(chat_id, "✅ Все напоминания отменены. Твоя лень победила.")

        elif text == "/status":
            user_data = get_user_data(chat_id)
            if user_data:
                chat_id_db, sleep_hour, sleep_minute, notifications_active, last_notification = user_data
                status = "включены" if notifications_active else "отключены"
                send_message(chat_id, 
                           f"📊 Твои настройки:\n"
                           f"⏰ Время сна: {sleep_hour:02d}:{sleep_minute:02d}\n"
                           f"🔔 Уведомления: {status}")
            else:
                send_message(chat_id, "❌ Время сна не установлено. Используй /setsleep")

        else:
            # Пытаемся распарсить время
            try:
                time_parts = text.strip().split(":")
                if len(time_parts) == 2:
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])

                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        # Сохраняем время сна в БД
                        save_user_data(chat_id, hour, minute, True)
                        
                        sleep_messages = [
                            f"⏰ Время сна установлено: {text}\nТвой личный таймер самоуничтожения запущен. Успей лечь — или бот придёт за тобой.",
                            f"⏰ Всё, обратный отсчёт пошёл: {text}\nНапоминания будут. Терпение — закончится. Спать — это приказ.",
                            f"⏰ Время сна зафиксировано: {text}\nРежим включён. Мягко не будет. Выключай всё и готовь тапочки."
                        ]
                        
                        selected_message = random.choice(sleep_messages)
                        send_message(chat_id, selected_message)
                        send_message(chat_id, "😈😈😈")
                    else:
                        send_message(chat_id, "❌ Неверный формат времени! Используй ЧЧ:ММ (например: 23:00)")
                else:
                    send_message(chat_id, "❌ Неверный формат! Введи время как ЧЧ:ММ")
            except ValueError:
                send_message(chat_id, "❌ Неверный формат времени! Используй ЧЧ:ММ (например: 23:00)")
                
    except Exception as e:
        print(f"❌ Ошибка обработки сообщения: {e}")

def handle_callback_query(callback_query):
    """Обрабатывает нажатия кнопок"""
    try:
        chat_id = callback_query["message"]["chat"]["id"]
        data = callback_query["data"]
        print(f"🔘 Callback от {chat_id}: {data}")

        if data == "going_to_sleep":
            # Отменяем уведомления
            update_user_notifications(chat_id, False)
            
            # Отвечаем на callback
            callback_id = callback_query["id"]
            url = BASE_URL + "answerCallbackQuery"
            make_request(url, {"callback_query_id": callback_id}, 'POST')

            # Редактируем сообщение
            message_id = callback_query["message"]["message_id"]
            url = BASE_URL + "editMessageText"
            make_request(url, {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "😴 Хорошо, напоминания остановлены.\nХоть что-то правильное сделал сегодня.\n\n💤 Спокойной ночи!"
            }, 'POST')
            
    except Exception as e:
        print(f"❌ Ошибка обработки callback: {e}")

def set_webhook():
    """Устанавливает webhook"""
    try:
        url = BASE_URL + "setWebhook"
        data = {"url": WEBHOOK_URL}
        result = make_request(url, data, 'POST')
        if result and result.get("ok"):
            print(f"✅ Webhook установлен: {WEBHOOK_URL}")
            return True
        else:
            print(f"❌ Ошибка установки webhook: {result}")
            return False
    except Exception as e:
        print(f"❌ Ошибка установки webhook: {e}")
        return False

def get_webhook_info():
    """Получает информацию о webhook"""
    try:
        url = BASE_URL + "getWebhookInfo"
        result = make_request(url)
        if result and result.get("ok"):
            print(f"ℹ️ Webhook info: {result['result']}")
        return result
    except Exception as e:
        print(f"❌ Ошибка получения webhook info: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Запуск бота...")
    
    # Инициализация
    init_db()
    
    # Устанавливаем webhook
    if set_webhook():
        # Проверяем webhook
        get_webhook_info()
        
        # Запускаем планировщик в отдельном потоке
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        
        # Запускаем Flask приложение
        port = int(os.environ.get("PORT", 5000))
        print(f"🌐 Запуск сервера на порту {port}")
        app.run(host="0.0.0.0", port=port, debug=False)
    else:
        print("❌ Не удалось установить webhook. Завершение работы.")
