import json
import requests
from .creditionals import BOT_URL, URL


def sentMessage(message_type, chat_id, text, reply_markup={}, parse_mode='HTML', link='', file_id=""):
    """ send message to telegram user with chat_id """

    if type(reply_markup) == list:
        reply_markup = {
            reply_markup[0]: [[{'text': i[0], 'callback_data': i[1], 'url': i[2]} for i in reply_markup[1][son]]
                              for son in range(len(reply_markup[1]))]
        }

    if message_type == "Message":
        return requests.post(BOT_URL + 'sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
        'reply_markup': json.dumps(reply_markup)
        }).json()
    elif message_type == "Photo":
        return requests.post(BOT_URL + 'sendPhoto', {
        'chat_id': chat_id,
        'caption': text,
        'photo': file_id,
        'parse_mode': parse_mode,
        'reply_markup': json.dumps(reply_markup)
        }).json()
    else:
        return requests.post(BOT_URL + 'sendPhoto', {
        'chat_id': chat_id,
        'caption': text,
        'video': file_id,
        'parse_mode': parse_mode,
        'reply_markup': json.dumps(reply_markup)
        }).json()
    

def answerCallbackQuery(callback_query_id, text, show_alert=False, url=""):
    '''Use this method to send answers to callback queries sent from inline keyboards. The answer will be displayed to the user as a notification at the top of the chat screen or as an alert. On success, True is returned.'''

    return requests.post(BOT_URL + 'answerCallbackQuery', {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert,
        "url": url
    }).json()


def getMemberInformation(chat_id, user_id):
    """ get information about member if he join chat"""

    result = requests.post(BOT_URL+ 'getChatMember', {
        'chat_id': chat_id,
        'user_id': user_id
    }).json()

    if 'result' in result:
        return result['result']['status']

    return ""


def forwardMessage(chat_id, from_chat_id, message_id):
    ''' forward message '''

    result = requests.post(BOT_URL + 'forwardMessage', {
        'chat_id': chat_id,
        'from_chat_id': from_chat_id,
        'message_id': message_id
    }).json()

    return result
