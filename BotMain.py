import telebot
import imaplib
import email
import schedule
import time
import sqlite3
import threading
from email.header import decode_header
from telebot import types
from datetime import datetime

# Токен бота Telegram
TOKEN = '6993475668:AAHhVM0-CdcpHWb12eTbKVo4X_7l9AsMlfY'

# Imap_Server
IMAP_SERVER = 'imap.mail.ru'

# Переменная-флаг
fl = 0

# Создание таблицы с данными о пользователях
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
   CREATE TABLE IF NOT EXISTS users (
       chat_id INTEGER PRIMARY KEY,
       email TEXT NOT NULL,
       password TEXT NOT NULL
   )
''')
conn.commit()

# Подключение к боту Telegram
bot = telebot.TeleBot(TOKEN)

# Список для хранения идентификаторов обработанных писем
processed_emails = {}


# Команды бота Telegram
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup()
    butn1 = types.KeyboardButton('Подключить почту к боту')
    markup.add(butn1)
    bot.reply_to(message, "Привет! Я бот, который будет пересылать тебе письма с почты.", reply_markup=markup)
    bot.register_next_step_handler(message, next_step)


def next_step(message):
    markup = types.ReplyKeyboardMarkup()
    butn1 = types.KeyboardButton('Как это сделать?')
    butn2 = types.KeyboardButton('Всё сделал')
    markup.row(butn1, butn2)
    if message.text == 'Подключить почту к боту':
        bot.send_message(message.chat.id,
                         'Отлично, для этого тебе понадобится включить "Доступ к Почте по IMAP", после чего получить "Пароль для внешних приложений"',
                         reply_markup=markup)
        bot.register_next_step_handler(message, handle_email_password)
    else:
        bot.send_message(message.chat.id, 'Для дальнейшей работы вам нужно подключить почту к боту🤷')
        bot.register_next_step_handler(message, next_step)


def handle_email_password(message):
    global fl
    if message.text == 'Как это сделать?':
        bot.send_message(message.chat.id,
                         'Всё очень просто! Воспользуйся нашим <a href="https://teletype.in/@letun/rn8pBWPlXyR">гайдом</a> и сможешь это легко сделать. Как всё сделаешь, отправь ответ в формате: почта пароль (где пароль это "Пароль для внешних приложений")',
                         parse_mode='html')
        bot.register_next_step_handler(message, handle_email_password)
    elif message.text == "Всё сделал":
        bot.send_message(message.chat.id,
                         'В таком случае отправь в формате: почта пароль (где пароль это "Пароль для внешних приложений")')
        bot.register_next_step_handler(message, handle_email_password)
    elif message.text.count(' ') == 1:
        email_addr, password = message.text.split()
        cursor.execute("REPLACE INTO users (chat_id, email, password) VALUES (?, ?, ?)",
                       (message.chat.id, email_addr, password))
        conn.commit()
        fl = 1
        try:
            mail = connect_to_mail(email_addr, password)
            markup = types.ReplyKeyboardMarkup()
            butn1 = types.KeyboardButton('Проверка последних 5 отправленных')
            butn2 = types.KeyboardButton('Проверка последних 5 входящих')
            butn3 = types.KeyboardButton('Отключить пересылку писем')
            markup.row(butn1, butn2)
            markup.add(butn3)
            bot.reply_to(message, 'Подключение успешно! Теперь бот будет пересылать вам письма.', reply_markup=markup)
            bot.register_next_step_handler(message, handle_user_choice)
        except Exception as e:
            bot.reply_to(message, f'Ошибка подключения: {e}')
    else:
        bot.reply_to(message, 'Неверный формат. Попробуйте снова.')
        bot.register_next_step_handler(message, handle_email_password)


def handle_user_choice(message):
    if message.text == 'Проверка последних 5 отправленных':
        show_recent_emails(message.chat.id, '&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-')
        bot.register_next_step_handler(message, handle_user_choice)
    elif message.text == 'Проверка последних 5 входящих':
        show_recent_emails(message.chat.id, 'INBOX')
        bot.register_next_step_handler(message, handle_user_choice)
    elif message.text == 'Отключить пересылку писем':
        disable_email_forwarding(message)
    else:
        bot.send_message(message.chat.id, 'Неизвестная команда. Попробуйте снова.')
        bot.register_next_step_handler(message, handle_user_choice)


def show_recent_emails(chat_id, folder):
    cursor.execute("SELECT email, password FROM users WHERE chat_id = ?", (chat_id,))
    user = cursor.fetchone()
    if not user:
        bot.send_message(chat_id, 'Почта не подключена.')
        return

    email_addr, password = user
    try:
        mail = connect_to_mail(email_addr, password)
        mail.select(folder)
        result, data = mail.search(None, "ALL")
        id_list = data[0].split()[-5:]  # последние 5 писем
        messages = []
        for email_id in reversed(id_list):
            result, msg_data = mail.fetch(email_id, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            subject = msg.get("Subject")
            if subject:
                subject = decode_header(subject)[0][0]
                if isinstance(subject, bytes):
                    subject = subject.decode()
            else:
                subject = "No Subject"

            sender_name, sender_email = email.utils.parseaddr(msg.get("From"))
            decoded_sender_name = decode_header(sender_name)[0][0]
            if isinstance(decoded_sender_name, bytes):
                decoded_sender_name = decoded_sender_name.decode()

            date_tuple = email.utils.parsedate_tz(msg['Date'])
            if date_tuple:
                local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                email_date = local_date.strftime("%Y-%m-%d %H:%M:%S")
            else:
                email_date = "Unknown Date"

            email_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                        email_body += part.get_payload(decode=True).decode()
            else:
                if msg.get_content_type() == "text/plain":
                    email_body = msg.get_payload(decode=True).decode()

            message = f"От: {decoded_sender_name} <{sender_email}>\nТема: {subject}\nДата: {email_date}\n\n{email_body}"
            messages.append(message)

        for msg in messages:
            bot.send_message(chat_id, msg)
    except Exception as e:
        bot.send_message(chat_id, f'Ошибка: {e}')


def disable_email_forwarding(message):
    chat_id = message.chat.id
    cursor.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
    conn.commit()
    markup = types.ReplyKeyboardMarkup()
    butn1 = types.KeyboardButton('Подключить почту к боту')
    markup.add(butn1)
    bot.send_message(chat_id, 'Пересылка писем отключена.', reply_markup=markup)
    bot.register_next_step_handler(message, next_step)


@bot.message_handler()
def send_error(message):
    bot.send_message(message.chat.id, "Неизвестная команда. Для подключения почты и работы с ботом воспользуйтесь командой /start")

# Подключение к почтовому ящику и поддержание соединения активным для каждого пользователя
def connect_to_mail(email, password):
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(email, password)
    return mail


# Основное тело для получения и обработки писем
def fetch_emails(mail, chat_id):
    try:
        mail.select("inbox")
        result, data = mail.search(None, "UNSEEN")  # Ищем только непрочитанные письма
        ids = data[0]
        id_list = ids.split()
        messages = []
        if id_list:
            for email_id in id_list:
                if email_id not in processed_emails.get(chat_id, set()):
                    result, msg_data = mail.fetch(email_id, "(RFC822)")
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    subject = msg.get("Subject")
                    if subject:
                        subject = decode_header(subject)[0][0]
                        if isinstance(subject, bytes):
                            subject = subject.decode()
                    else:
                        subject = "No Subject"

                    sender_name, sender_email = email.utils.parseaddr(msg.get("From"))
                    decoded_sender_name = decode_header(sender_name)[0][0]
                    if isinstance(decoded_sender_name, bytes):
                        decoded_sender_name = decoded_sender_name.decode()

                    date_tuple = email.utils.parsedate_tz(msg['Date'])
                    if date_tuple:
                        local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                        email_date = local_date.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        email_date = "Unknown Date"

                    email_body = ""
                    attachments = []  # Список для хранения вложений

                    # Получаем вложения
                    for part in msg.walk():
                        if part.get_content_maintype() == "multipart":
                            continue
                        filename = part.get_filename()
                        if filename:
                            attachment = part.get_payload(decode=True)
                            attachments.append((filename, attachment))

                    # Отправляем вложения в Telegram
                    for filename, attachment in attachments:
                        bot.send_document(chat_id, attachment)

                    # Формируем сообщение с информацией о письме (без вложений)
                    email_body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                                email_body += part.get_payload(decode=True).decode()
                    else:
                        if msg.get_content_type() == "text/plain":
                            email_body = msg.get_payload(decode=True).decode()

                    message = f"От: {decoded_sender_name} <{sender_email}>\nТема: {subject}\nДата: {email_date}\n\n{email_body}"
                    messages.append(message)

                    # Помечаем письмо как обработанное
                    if chat_id not in processed_emails:
                        processed_emails[chat_id] = set()
                    processed_emails[chat_id].add(email_id)

        return messages

    except Exception as e:
        print(f"Ошибка при получении писем для {chat_id}: {e}")
        return []


def send_email_updates():
    if fl == 1:
        cursor.execute("SELECT chat_id, email, password FROM users")
        users = cursor.fetchall()
        for chat_id, email, password in users:
            try:
                mail = connect_to_mail(email, password)
                email_messages = fetch_emails(mail, chat_id)
                if email_messages:
                    for email_message in email_messages:
                        bot.send_message(chat_id, email_message)
            except Exception as e:
                print(f"Ошибка при отправке писем для {chat_id}: {e}")


# Функция для отправки NOOP команды
def keep_mail_connection_alive():
    if fl == 1:
        while True:
            cursor.execute("SELECT email, password FROM users")
            users = cursor.fetchall()
            for email, password in users:
                try:
                    mail = connect_to_mail(email, password)
                    mail.noop()
                except Exception as e:
                    print(f"Ошибка при поддержании соединения для {email}: {e}")
            time.sleep(300)  # Отправляем команду NOOP каждые 5 минут


# Запуск телеграмм бота в отдельном потоке
def telegram_bot_polling():
    bot.infinity_polling()


# Запуск планировщика в основном потоке
def start_scheduler():
    schedule.every(5).seconds.do(send_email_updates)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    # Запуск телеграмм бота
    threading.Thread(target=telegram_bot_polling).start()
    # Запуск функции для поддержания соединения с почтой
    threading.Thread(target=keep_mail_connection_alive).start()
    # Запуск планировщика
    start_scheduler()
