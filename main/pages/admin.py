from django.contrib import admin
from .models import BotUser, ChannelBot, AboutMessage, ChannelMessage, GroupBot, AutoAnswer
from .models import Service, Doctor, ClinicInfo, FAQ

# Register your models here.
admin.site.register(BotUser)
admin.site.register(ChannelBot)
admin.site.register(AboutMessage)
admin.site.register(ChannelMessage)
admin.site.register(GroupBot)
admin.site.register(AutoAnswer)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "currency", "is_active", "updated_at")
    list_editable = ("price", "currency", "is_active")
    search_fields = ("name", "category")


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "specialty", "is_active", "updated_at")
    list_editable = ("is_active",)
    search_fields = ("full_name", "specialty")


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "is_active", "updated_at")
    list_editable = ("is_active",)
    search_fields = ("question", "answer")


admin.site.register(ClinicInfo)