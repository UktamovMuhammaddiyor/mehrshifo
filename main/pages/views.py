from django.shortcuts import render, HttpResponse
import requests
from .creditionals import BOT_URL, URL
from django.views.decorators.csrf import csrf_exempt
import json
from .TelegramAPI import sentMessage, getMemberInformation, answerCallbackQuery, forwardMessage
from .models import BotUser, AboutMessage, ChannelBot, ChannelMessage


# Create your views here.
def index(request):

    return HttpResponse("Hello Wolrd")


def setWebHook(request):
    """ set webhook for telegram API on URL """

    response = requests.post(BOT_URL + 'setwebhook?url=' + URL).json()
    return HttpResponse(response)


@csrf_exempt
def getPost(request):
    if request.method == 'POST':
        """ reply sent message from user """

        response = json.loads(request.body)
        message = AboutMessage.objects.all()

        if message:
            message = message[0]

        if 'message' in response:
            response = response['message']

            if "text" in response:
                text = response['text']
                if text == "/start":
                    user = getUser(response)
                else:
                    user = BotUser.objects.get(user_id=response["from"]["id"])

                    if text == '/getadmin':
                        user.status = 'getAdmin'
                        sentMessage('Message', user.user_id, 'Iltimos parolni kiriting:')
                    elif user.status == 'getAdmin':
                        if text == 'WTlJgvNGS3PZGOv':
                            user.status = ''
                            user.is_admin = True
                            reply_markup = {
                                'keyboard': [[{'text': '/addchannel'}], [{'text': '/addChannelPost'}], [{'text': '/createMainPost'}], [{'text': '/addPost'}]],
                                'resize_keyboard': True,
                            }

                            requests.post(BOT_URL + 'sendMessage', {
                                'chat_id': user.user_id,
                                'text': "Siz endi adminsiz.",
                                'reply_markup': json.dumps(reply_markup)
                                }).json()
                        else:
                            sentMessage('Message', user.user_id, "Parol nato'g'ri")
                            user.status = ''
                    elif not user.is_admin:
                        pass
                    elif text == '/addchannel':
                        user.status = 'addingChannel'
                        sentMessage('Message', user.user_id, "Shu botni kanalga admibn qilib qo'shing va kanal usernamini jo'nating: ")
                    elif user.status == 'addingChannel':
                        chat = ChannelBot.objects.filter(chat_link=text)
                        if chat:
                            user.status = ''
                            messages = AboutMessage.objects.all()
                            for i in messages:
                                i.delete()
                            AboutMessage.objects.create(link=chat[0].chat_link, chat_id=chat[0].chat_id)
                            sentMessage('Message', user.user_id, "Kanal qo'shildi.")
                        else:
                            sentMessage('Message', user.user_id, "Bot kanalga qo'shilmagan yoki admin emas.")
                    elif text == '/createMainPost':
                        user.status = 'creatingmainpost'
                        sentMessage('Message', user.user_id, "Postni jo'nating")
                    elif user.status == 'creatingmainpost':
                        message.message = text
                        message.message_id = response['message_id']
                        user.status = ''
                    elif user.status == 'addingAnswer':
                        message.answer = text
                        user.status = ''
                        sentMessage("Message", user.user_id, "Assosiy post qo'shildi.!")
                    elif text == '/addPost':
                        user.status = 'addingPost'
                        sentMessage('Message', user.user_id, "Postni jo'nating.")
                    elif user.status == "addingPost":
                        user.status = ''
                        users = BotUser.objects.all()
                        for chat_id in users:
                            forwardMessage(chat_id.user_id, user.user_id, response['message_id'])
                        sentMessage('Message', user.user_id, "Habar hammaga jo'natildi.")
                    elif text == '/addChannelPost':
                        user.status = 'addingChannelPost'
                        sentMessage('Message', user.user_id, "Postni jo'nating.")
                    elif user.status == 'addingPostAnswer':
                        user.status = ''
                        channel_message = ChannelMessage.objects.first()
                        sentMessage(channel_message.message_type, channel_message.chat_id, channel_message.message, ['inline_keyboard', [[["Javobini bilish", "done", ""]]]], file_id=channel_message.file_id)
                        sentMessage("Message", user.user_id, "Post kanalga jo'natildi.")
                    elif user.status == 'addingChannelPost':
                        channel_messages = ChannelMessage.objects.all()
                        for channel_message in channel_messages:
                            channel_message.delete()

                        channel_message = ChannelMessage.objects.create(message=text)
                        channel_message.message_type = 'Message'
                        channel_message.chat_id = message.chat_id
                        channel_message.save()

                        user.status = 'addingPostAnswer'
                        sentMessage("Message", user.user_id, "Post uchun javobni qo'shing.")

                    if message:
                        message.save()

                    user.save()
            else:
                user = BotUser.objects.get(user_id=response["from"]["id"])
                file_id = ''
                m_type = ''

                if user.status == 'creatingmainpost':
                    if 'photo' in response:
                        file_id = response['photo'][-1]['file_id']
                        m_type = 'Photo'
                    elif 'video' in response:
                        file_id = response['photo'][-1]['file_id']
                        m_type = 'Video'

                    message.file_id = file_id
                    message.message = response['caption']
                    message.message_type = m_type
                    message.message_id = response['message_id']
                    message.save()
                    user.status = 'addingAnswer'
                    sentMessage("Message", user.user_id, "Post uchun javobni qo'shing.")
                elif user.status == "addingPost":
                    user.status = ''
                    users = BotUser.objects.all()
                    for chat_id in users:
                        forwardMessage(chat_id.user_id, user.user_id, response['message_id'])
                    sentMessage('Message', user.user_id, "Habar hammaga jo'natildi.")
                elif user.status == 'addingChannelPost':

                    if 'photo' in response:
                        file_id = response['photo'][-1]['file_id']
                        m_type = 'Photo'
                    elif 'video' in response:
                        file_id = response['photo'][-1]['file_id']
                        m_type = 'Video'

                    channel_messages = ChannelMessage.objects.all()
                    for channel_message in channel_messages:
                        channel_message.delete()

                    channel_message = ChannelMessage.objects.create()
                    channel_message.message = response['caption']
                    channel_message.file_id = file_id
                    channel_message.message_type = m_type
                    channel_message.chat_id = message.chat_id
                    channel_message.save()
                    user.status = 'addingPostAnswer'
                    sentMessage("Message", user.user_id, "Post uchun javobni qo'shing.")
                    
                user.save()
            if user.status == "" and message:
                sentMessage(message.message_type, user.user_id, message.message, ['inline_keyboard', [[["Kanalga azo bo'lish", 'member', f'{message.link}']], [["Javobini bilish", "done", ""]]]], file_id=message.file_id)
        elif 'callback_query' in response:
            response = response['callback_query']
            if userHasMemberOfChannel(message.chat_id, response['from']['id']) :
                answerCallbackQuery(response['id'], message.answer, True)
            else:
                answerCallbackQuery(response['id'], "Javobni bilish uchun iltimos kanalga a'zo blo'ling.", True)
        elif 'my_chat_member' in response:
            response = response['my_chat_member']['chat']
            try:
                ChannelBot.objects.get(chat_id=response['id'])
            except: 
                ChannelBot.objects.create(name=response['title'], chat_link=f"https://t.me/{response['username']}", chat_id=response['id'])
    return HttpResponse('working')


def getUser(response, user=None):
    """ create user or get user """

    try:
        BotUser.objects.get(user_id=response['from']['id'])
    except:
        BotUser.objects.create(user_id=response['from']['id'], name=response['from']['first_name'])

    return user


def userHasMemberOfChannel(chat_id, user_id):
    '''check user is member of channel'''

    result = getMemberInformation(chat_id, user_id)

    if result == "member" or result == "creator" or result == "admin":
        return True
    
    return False