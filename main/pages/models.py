from django.db import models

# Create your models here.
class BotUser(models.Model):
    name = models.CharField(max_length=255)
    user_id = models.IntegerField()
    user_name = models.CharField(max_length=255)
    is_admin = models.BooleanField(default=False)
    status = models.CharField(max_length=255, default="")

    def __str__(self) -> str:
        return self.name


class AboutMessage(models.Model):
    link = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    message_type = models.CharField(max_length=15, default="Message", blank=True)
    chat_id = models.IntegerField(blank=True)
    file_id = models.CharField(max_length=255, default=0, blank=True)
    message_id = models.IntegerField(default=0, blank=True)
    answer = models.CharField(max_length=255, default="", blank=True)

    def __str__(self) -> str:
        return self.link
    

class ChannelMessage(models.Model):
    message = models.TextField(blank=True)
    message_type = models.CharField(max_length=15, default="Message", blank=True)
    chat_id = models.IntegerField(default=0)
    file_id = models.CharField(max_length=255, default=0, blank=True)
    answer = models.CharField(max_length=255, default="", blank=True)

    def __str__(self) -> str:
        return f"{self.chat_id}"
    

class ChannelBot(models.Model):
    name = models.CharField(max_length=255)
    chat_link = models.CharField(max_length=255)
    chat_id = models.IntegerField()

    def __str__(self) -> str:
        return self.name