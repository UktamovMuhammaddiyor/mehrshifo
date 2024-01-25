from django.contrib import admin
from .models import BotUser, ChannelBot, AboutMessage

# Register your models here.
admin.site.register(BotUser)
admin.site.register(ChannelBot)
admin.site.register(AboutMessage)