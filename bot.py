import telebot
import requests
from creds.creds import get_bot_token, get_creds
import logging
from config import *
from yandex_gpt import ask_gpt
from database import create_database, add_message, select_n_last_messages
from validators import *
from gpt import *


bot = telebot.TeleBot(get_bot_token())

create_database()
iam_token, folder_id = get_creds()

logging.basicConfig(filename=LOGS, level=logging.ERROR, format="%(asctime)s FILE: %(filename)s IN: %(funcName)s MESSAGE: %(message)s", filemode="w")


@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    bot.send_message(user_id, text=
                     'Привет! Я - бот голосовой ассистент! \nЧтобы узнать, что я умею, нажми /help.')


@bot.message_handler(commands=['help'])
def help(message):
    user_id = message.from_user.id
    bot.send_message(user_id, text=
                     'Я бот, помогающий пользователям при помощи GPT.\nОтправь мне голосовое сообщение или текст.')


@bot.message_handler(commands=['debug'])
def debug(message):
    f = open('logs.txt', 'rb')
    bot.send_document(message.chat.id, f)


@bot.message_handler(content_types=['text'])
def text_messages(message):
    try:
        user_id = message.from_user.id
        status_check, error_message = number_of_users(user_id)
        if not status_check:
            bot.send_message(user_id, error_message)
            return
        user_message = [message.text, 'user', 0, 0, 0]
        add_message(user_id=user_id, full_message=user_message)
        last_4_messages, spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        gpt_tokens, error_message = is_gpt_tokens_limit(last_4_messages, spent_tokens)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        status_gpt, gpt_answer, answer_tokens = ask_gpt(last_4_messages)
        if not status_gpt:
            bot.send_message(user_id, gpt_answer)
            return
        gpt_tokens += answer_tokens
        gpt_message = [gpt_answer, 'assistant', gpt_tokens, 0, 0]
        add_message(user_id=user_id, full_message=gpt_message)
        bot.send_message(user_id, gpt_answer, reply_to_message_id=message.id)
    except Exception as err:
        logging.error(err)
        bot.send_message(message.from_user.id, 'Не получилось ответить. Попробуйте написать сообщение снова.')


def is_gpt_tokens_limit(all_token, chat_id):
    # Получаем из таблицы размер текущей сессии в токенах
    try:
        tokens_of_user = all_token

        # В зависимости от полученного числа выводим сообщение
        if tokens_of_user >= MAX_USER_GPT_TOKENS:
                bot.send_message(
                    chat_id,
                    f'Вы израсходовали все токены в этой сессии. Вы можете начать новую, введя help_with')
                return True

        elif tokens_of_user + 50 >= MAX_USER_GPT_TOKENS:  # Если осталось меньше 50 токенов
            bot.send_message(
                chat_id,
                f'Вы приближаетесь к лимиту в {MAX_USER_GPT_TOKENS} токенов в этой сессии. '
                f'Ваш запрос содержит суммарно {tokens_of_user} токенов.')

        elif tokens_of_user / 2 >= MAX_USER_GPT_TOKENS:  # Если осталось меньше половины
            bot.send_message(
                chat_id,
                f'Вы использовали больше половины токенов в этой сессии. '
                f'Ваш запрос содержит суммарно {tokens_of_user} токенов.'
            )
        return False
    except Exception as e:
        logging.error(f"Ошибка подсчета токенов {e}")


def stt(data):
    # указываем параметры запроса
    params = "&".join([
        "topic=general",  # используем основную версию модели
        f"folderId={folder_id}",
        "lang=ru-RU"  # распознаём голосовое сообщение на русском языке
    ])
    url = f"https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?{params}"
    # аутентификация через IAM-токен
    headers = {
        'Authorization': f'Bearer {iam_token}',
    }
    # выполняем запрос
    response = requests.post(url=url, headers=headers, data=data)
    # преобразуем json в словарь
    decoded_data = response.json()
    # проверяем не произошла-ли ошибка при запросе
    if decoded_data.get("error_code") is None:
        return True, decoded_data.get("result")  # возвращаем статус и текст из аудио
    else:
        return False, "При запросе в SpeechKit возникла ошибка"


def is_stt_block_limit(user_id, duration):
    audio_blocks = math.ceil(duration / 15)  # переводим секунды в аудиоблоки и округляем в большую сторону
    all_blocks = count_all_limits(user_id, 'stt_blocks') + audio_blocks

    # проверяем, что аудио длится меньше 30 секунд
    if duration >= 30:
        return None, "SpeechKit STT работает с голосовыми сообщениями меньше 30 секунд"

    # сравниваем all_blocks с количеством доступных пользователю аудиоблоков
    if all_blocks > MAX_USER_STT_BLOCKS:
        return None, f"Превышен общий лимит SpeechKit STT {MAX_USER_STT_BLOCKS}"

    # если всё ок - возвращаем размер этого голосового сообщения
    return audio_blocks, ""


def is_tts_symbol_limit(message, text):
    user_id = message.from_user.id
    text_symbols = len(text)

    # Функция из БД для подсчёта всех потраченных пользователем символов
    all_symbols = count_all_limits(user_id, 'tts_symbols') + text_symbols

    # Сравниваем all_symbols с количеством доступных пользователю символов
    if all_symbols >= MAX_USER_TTS_SYMBOLS:
        msg = f"Превышен общий лимит Speechkit TTS {MAX_USER_TTS_SYMBOLS}. Использовано: {all_symbols} символов. Доступно: {MAX_USER_TTS_SYMBOLS - all_symbols}"
        bot.send_message(user_id, msg)
        return None
    return len(text)


def f(message):
    return False

@bot.message_handler(func=f)
def tts(message):
    headers = {
        'Authorization': f'Bearer {iam_token}',
    }
    user_id = message.from_user.id
    data = {
        'text': message.text,
        'lang': 'ru-RU',
        'voice': 'jane',
        'emotion': 'neutral',
        'speed': 1,
        'folderId': "b1gt7jnsj37mr38s5k25",
    }
    response = requests.post('https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize', headers=headers, data=data)

    if response.status_code == 200:
        bot.send_voice(message.chat.id, response.content)
    else:
        bot.send_message(chat_id=user_id, text=f'Ошибка {response.status_code}')


@bot.message_handler(content_types=['voice'])
def voice_messages(message):
    try:
        user_id = message.from_user.id
        status_check_users, error_message = number_of_users(user_id)
        if not status_check_users:
            bot.send_message(user_id, error_message)
            return
        stt_blocks, error_message = is_stt_block_limit(user_id, message.voice.duration)
        if error_message:
            bot.send_message(user_id, error_message)
        file_id = message.voice.file_id
        file_info = bot.get_file(file_id)
        file = bot.download_file(file_info.file_path)
        status_stt, stt_text = stt(file)
        if not status_stt:
            bot.send_message(user_id, stt_text)
            return
        add_message(user_id=user_id, full_message=[stt_text, 'user', 0, 0, stt_blocks])
        last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        total_gpt_tokens, error_message = is_gpt_tokens_limit(last_messages, total_spent_tokens)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        last_4_messages, spent_tokens, = select_n_last_messages(user_id, COUNT_LAST_MSG)
        gpt_status, gpt_answer, answer_tokens = ask_gpt(last_4_messages)
        if not gpt_status:
            bot.send_message(user_id, gpt_answer)
            return
        total_gpt_tokens += answer_tokens

        tts_symbols, error_message = is_tts_symbol_limit(user_id, gpt_answer)
        add_message(user_id=user_id, full_message=[gpt_answer, 'assistant', total_gpt_tokens, tts_symbols, 0])
        if error_message:
            bot.send_message(user_id, error_message)

        status_tts, voice_response = tts(gpt_answer)
        if not status_tts:
            bot.send_message(user_id, gpt_answer,reply_to_message_id=message.id)
        else:
            bot.send_voice(user_id, voice_response, reply_to_message_id=message.id)

    except Exception as err:
        logging.error(err)
        bot.send_message(message.from_user.id, 'Не получилось ответить. Пожалуйста, отправьте ваше сообщение снова.')


bot.polling(none_stop=True)