import telebot
import requests
from creds import get_bot_token, get_creds
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

def f(message):
    return False

@bot.message_handler(func=f)
def tts(message):
    iam_token = "t1.9euelZqKxorMnceXzo3JxpKdm4-Uze3rnpWakcebx83GmJiSm5zMjcbKks7l8_caODxO-e92fD4F_t3z91pmOU7573Z8PgX-zef1656Vmomai8_KmYubksbLkJGOxpGR7_zF656Vmomai8_KmYubksbLkJGOxpGRveuelZqWjJSTyoyXjY6Txp3HlZKNybXehpzRnJCSj4qLmtGLmdKckJKPioua0pKai56bnoue0oye.lxtF20Pd00GESbsIQVR8NmaCSJeb1EoGjo5EcS0BRosXrN7--z59bdKTpK5w_xDTqEltRQ2iBaqAEjc2mhhDBw"
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
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        last_4_messages, spent_tokens, = select_n_last_messages(user_id, COUNT_LAST_MSG)
        gpt_status, gpt_answer = ask_gpt(last_4_messages)
        if not gpt_status:
            bot.send_message(user_id, gpt_answer)
            return


        status_tts, voice_response = tts(gpt_answer)
        if not status_tts:
            bot.send_message(user_id, gpt_answer,reply_to_message_id=message.id)
        else:
            bot.send_voice(user_id, voice_response, reply_to_message_id=message.id)

    except Exception as err:
        logging.error(err)
        bot.send_message(message.from_user.id, 'Не получилось ответить. Пожалуйста, отправьте ваше сообщение снова.')





bot.polling(none_stop=True)