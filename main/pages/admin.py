from django.contrib import admin
from .models import BotUser, ChannelBot, AboutMessage, ChannelMessage, GroupBot, AutoAnswer

# Register your models here.
admin.site.register(BotUser)
admin.site.register(ChannelBot)
admin.site.register(AboutMessage)
admin.site.register(ChannelMessage)
admin.site.register(GroupBot)
admin.site.register(AutoAnswer)