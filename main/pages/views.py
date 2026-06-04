from django.shortcuts import render, HttpResponse
import requests
from .creditionals import BOT_URL, URL, BOT_ADMIN_PASSWORD
from django.views.decorators.csrf import csrf_exempt
import json
from .TelegramAPI import sentMessage, getMemberInformation, answerCallbackQuery, forwardMessage, deleteMessage
from .models import BotUser, AboutMessage, ChannelBot, ChannelMessage, GroupBot, AutoAnswer, AISettings, Conversation



def _is_allowlisted(user_id):
    """AI/admin commands: allow if the allowlist is empty (back-compat) or contains the id."""
    from .creditionals import ADMIN_USER_IDS
    return (not ADMIN_USER_IDS) or (user_id in ADMIN_USER_IDS)


# Create your views here.
def index(request):

    return HttpResponse("Hello Wolrd")


def setWebHook(request):
    """ set webhook for telegram API on URL """

    from .creditionals import TELEGRAM_WEBHOOK_SECRET
    response = requests.post(BOT_URL + 'setWebhook', {
        'url': URL,
        'secret_token': TELEGRAM_WEBHOOK_SECRET,
    }).json()
    return HttpResponse(response)


@csrf_exempt
def getPost(request):
    if request.method == 'POST':
        """ reply sent message from user """

        from .creditionals import TELEGRAM_WEBHOOK_SECRET
        from .models import ProcessedUpdate

        if TELEGRAM_WEBHOOK_SECRET:
            if request.headers.get('X-Telegram-Bot-Api-Secret-Token', '') != TELEGRAM_WEBHOOK_SECRET:
                return HttpResponse('forbidden', status=403)

        response = json.loads(request.body)

        update_id = response.get('update_id')
        if update_id is not None:
            _, created = ProcessedUpdate.objects.get_or_create(update_id=update_id)
            if not created:
                return HttpResponse('duplicate')

        message = AboutMessage.objects.all()

        if message:
            message = message[0]

        if 'message' in response:
            response = response['message']

            if response['chat']['type'] == 'supergroup' or response['chat']['type'] == 'group' or response['chat']['type'] == 'channel':
                if 'reply_to_message' in response:
                    if response['reply_to_message'].get('text') == "Iltimos guruhni qo'shish uchun parolni tering.":
                        if response["text"] == BOT_ADMIN_PASSWORD:
                            group = GroupBot.objects.filter(group_id=response['chat']['id'])
                            if group:
                                group[0].is_active = True
                                group[0].save()
                                requests.post(BOT_URL + 'sendMessage', {
                                    'chat_id': response['chat']['id'],
                                    'text': "Guruh activlashtirildi.",
                                    'reply_parameters': json.dumps({
                                        'message_id': response['message_id'],
                                    }),
                                })
                                deleteMessage(response['chat']['id'], response['reply_to_message']['message_id'])
                            else:
                                requests.post(BOT_URL + 'sendMessage', {
                                    'chat_id': response['chat']['id'],
                                    'text': "Guruh topilmadi botni guruhga boshqattan qo'shing.",
                                    'reply_parameters': json.dumps({
                                        'message_id': response['message_id'],
                                    }),
                                })
                        else:
                            requests.post(BOT_URL + 'sendMessage', {
                                'chat_id': response['chat']['id'],
                                'text': "Parol nato'g'ri",
                                'reply_parameters': json.dumps({
                                    'message_id': response['message_id'],
                                }),
                            })
                    else:
                        from .handlers.group import handle_group_message
                        handle_group_message(response)
            elif "text" in response:
                text = response['text']
                if text == "/start":
                    user = getUser(response)
                    if message:
                        sentMessage(message.message_type, user.user_id, message.message, ['inline_keyboard', [[["Kanalga azo bo'lish", 'member', f'{message.link}']], [["Tekshirish", "check", ""]]]], file_id=message.file_id)
                else:
                    user = BotUser.objects.get(user_id=response["from"]["id"])

                    if text == '/getadmin':
                        user.status = 'getAdmin'
                        sentMessage('Message', user.user_id, 'Iltimos parolni kiriting:')
                    elif user.status == 'getAdmin':
                        if text == BOT_ADMIN_PASSWORD:
                            user.status = ''
                            user.is_admin = True
                            reply_markup = {
                                'keyboard': [[{'text': '/addchannel'}, {'text': '/addChannelPost'}], [{'text': '/createMainPost'}], [{'text': '/addPost'}], [{'text': '/subcription'}, {'text': '/addAnswer'}]],
                                'resize_keyboard': True,
                            }

                            from .creditionals import MINIAPP_URL
                            if MINIAPP_URL:
                                reply_markup['keyboard'].append(
                                    [{'text': "✍️ Kontent", 'web_app': {'url': MINIAPP_URL}}]
                                )

                            requests.post(BOT_URL + 'sendMessage', {
                                'chat_id': user.user_id,
                                'text': "Siz endi adminsiz.",
                                'reply_markup': json.dumps(reply_markup)
                                }).json()
                        else:
                            sentMessage('Message', user.user_id, "Parol nato'g'ri")
                            user.status = ''
                    elif not user.is_admin:
                        result = True
                        if message:
                            if message.is_active:
                                if userHasMemberOfChannel(message.chat_id, user.user_id):
                                    user.is_subcribe = True
                                else:
                                    result = False
                                    sentMessage("Message", user.user_id, "Iltimos botdan foydalanish uchun kanalga obuna bo'ling", ['inline_keyboard', [[["Kanalga azo bo'lish", 'member', f'{message.link}']], [["Tekshirish", "check", ""]]]])
                        if result:
                            from django_q.tasks import async_task
                            async_task('pages.tasks.process_client_message',
                                       user.user_id, text, response['message_id'])
                    elif text == '/subcription':
                        sentMessage("Message", user.user_id, "Majburiy obuna", ['inline_keyboard', [[["Yoqish", 'turn_on_subcription', '']], [["O'chirish", "turn_off_subcription", ""]]]])
                    elif text == '/ai_on':
                        if _is_allowlisted(user.user_id):
                            s = AISettings.get(); s.is_enabled = True; s.save()
                            sentMessage("Message", user.user_id, "AI yoqildi.")
                    elif text == '/ai_off':
                        if _is_allowlisted(user.user_id):
                            s = AISettings.get(); s.is_enabled = False; s.save()
                            sentMessage("Message", user.user_id, "AI o'chirildi.")
                    elif text == '/ai_status':
                        if _is_allowlisted(user.user_id):
                            from django.core.cache import cache
                            from .ai.pipeline import _daily_key
                            s = AISettings.get()
                            calls = cache.get(_daily_key()) or 0
                            handoffs = Conversation.objects.filter(status='handoff').count()
                            sentMessage("Message", user.user_id,
                                        f"AI: {'ON' if s.is_enabled else 'OFF'}\nModel: {s.model_name}\n"
                                        f"Bugungi chaqiruvlar: {calls}\nHandoff suhbatlar: {handoffs}")
                    elif text == "/addAnswer":
                        user.status = 'addinganswer'
                        sentMessage('Message', user.user_id, "Iltimos javobni jo'nating.")
                    elif user.status == 'addinganswer':
                        user.status = ''
                        answer = AutoAnswer.objects.all()
                        if answer:
                            answer[0].text = text
                            answer[0].save()
                        else:
                            AutoAnswer.objects.create(text=text)
                        sentMessage("Message", user.user_id, "Auto javob qo'shildi.")
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
                        channel_message.answer = text
                        channel_message.save()
                        result = sentMessage(channel_message.message_type, channel_message.chat_id, channel_message.message, ['inline_keyboard', [[["Javobini bilish", f"checkAnswer-{channel_message.id}", ""]]]], file_id=channel_message.file_id)
                        if 'result' in result:
                            sentMessage("Message", user.user_id, f"Post kanalga jo'natildi.\nPost linki \n<code>https://t.me/{result['result']['sender_chat']['username']}/{result['result']['message_id']}</code>")
                    elif user.status == 'addingChannelPost':
                        channel_messages = ChannelMessage.objects.all()
                        for channel_message in channel_messages:
                            channel_message.delete()

                        channel_message = ChannelMessage.objects.create(message=text)
                        channel_message.message_type = 'Message'
                        if message.chat_id:
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
                    if message.chat_id:
                        channel_message.chat_id = message.chat_id
                    channel_message.save()
                    user.status = 'addingPostAnswer'
                    sentMessage("Message", user.user_id, "Post uchun javobni qo'shing.")
                    
                user.save()
        elif 'callback_query' in response:
            response = response['callback_query']
            data = response['data']
            if data[:12] == "checkAnswer-":
                channel_message = ChannelMessage.objects.first()
                if userHasMemberOfChannel(channel_message.chat_id, response['from']['id']) :
                    answerCallbackQuery(response['id'], channel_message.answer, True)
                else:
                    answerCallbackQuery(response['id'], "Javobni bilish uchun iltimos kanalga a'zo bo'ling.", True)
            elif data == 'turn_on_subcription':
                if message:
                    message.is_active = True
                    message.save()
                sentMessage("Message", response['from']['id'], "Majburiy obuna yoqildi.")
                deleteMessage(response['from']['id'], response['message']['message_id'])
            elif data == 'turn_off_subcription':
                if message:
                    message.is_active = False
                    message.save()
                sentMessage("Message", response['from']['id'], "Majburiy obuna o'chirildi.")
                deleteMessage(response['from']['id'], response['message']['message_id'])
            elif data == 'done':
                if message and userHasMemberOfChannel(message.chat_id, response['from']['id']) :
                    answerCallbackQuery(response['id'], message.answer, True)
                else:
                    answerCallbackQuery(response['id'], "Javobni bilish uchun iltimos kanalga a'zo bo'ling.", True)
            elif data == 'check':
                if message and userHasMemberOfChannel(message.chat_id, response['from']['id']) :
                    bot_user = BotUser.objects.get(user_id=response['from']['id'])
                    bot_user.is_subcribe = True
                    bot_user.save()
                    answerCallbackQuery(response['id'], "Siz kanalga a'zo bo'libsiz. Endi bemalol botdan foydlanishingiz mumkin. Raxmat!!!", True)
                else:
                    answerCallbackQuery(response['id'], "Botga yozish uchun iltimos kanalga a'zo bo'ling.", True)
        elif 'my_chat_member' in response:
            result = response['my_chat_member']['chat']
            response = response['my_chat_member']
            if result['type'] == 'channel':
                try:
                    ChannelBot.objects.get(chat_id=result['id'])
                except: 
                    if 'username' in result:
                        ChannelBot.objects.create(name=result['title'], chat_link=f"https://t.me/{result['username']}", chat_id=result['id'])
                    else:
                        ChannelBot.objects.create(name=result['title'], chat_id=result['id'])
            elif result['type'] == "group" or result['type'] == "supergroup":
                if response['new_chat_member']['status'] == "administrator":
                    try:
                        group = GroupBot.objects.get(group_id=result['id'])
                    except: 
                        if 'username' in result:
                            group = GroupBot.objects.create(name=result['title'], group_link=f"https://t.me/{result['username']}", group_id=result['id'])
                        else:
                            group = GroupBot.objects.create(name=result['title'], group_id=result['id'])
                    sentMessage('Message', group.group_id, "Iltimos guruhni qo'shish uchun parolni tering.")

    return HttpResponse('working')


def getUser(response, user=None):
    """ create user or get user """

    try:
        user = BotUser.objects.get(user_id=response['from']['id'])
    except:
        user = BotUser.objects.create(user_id=response['from']['id'], name=response['from']['first_name'])

    return user


def userHasMemberOfChannel(chat_id, user_id):
    '''check user is member of channel'''

    result = getMemberInformation(chat_id, user_id)

    if result == "member" or result == "creator" or result == "admin":
        return True
    
    return False