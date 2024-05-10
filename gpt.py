import logging
import math
from config import LOGS, MAX_USERS,MAX_USER_GPT_TOKENS
from database import count_users, count_all_limits
from yandex_gpt import count_gpt_tokens

logging.basicConfig(filename=LOGS, level=logging.ERROR, format="%(asctime)s FILE: %(filename)s IN: %(funcName)s MESSAGE: %(message)s", filemode="w")


def is_gpt_tokens_limit(messages, total_tokens):
    all_tokens = count_gpt_tokens(messages)
    if all_tokens > MAX_USER_GPT_TOKENS:
        return None, f'Превышен общий лимит токенов, равный {MAX_USER_GPT_TOKENS}'
    else:
        return all_tokens


def number_of_users(user_id):
    count = count_users(user_id)
    if count is None:
        return None, 'Ошибка при работе с базой данных'
    if count > MAX_USERS:
        return 'Превышено максимальное количество пользователей'
    else:
        return True, ''


