from django.contrib import admin
from django.http import HttpResponse
from .models import BotUser, ChannelBot, AboutMessage, ChannelMessage, GroupBot, AutoAnswer
from .models import Service, Doctor, ClinicInfo, FAQ
from .models import AISettings, AIDecisionLog
from .knowledge.snapshot import get_kb_snapshot


@admin.action(description="Preview assembled KB (what the AI sees)")
def preview_kb(modeladmin, request, queryset):
    return HttpResponse(get_kb_snapshot(), content_type="text/plain; charset=utf-8")

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
    actions = [preview_kb]


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


admin.site.register(AISettings)


@admin.register(AIDecisionLog)
class AIDecisionLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "intent", "confidence", "action")
    list_filter = ("action", "intent")
    readonly_fields = [f.name for f in AIDecisionLog._meta.fields]

    def has_add_permission(self, request):
        return False


from .models import FAQSuggestion


@admin.action(description="Approve → create FAQ")
def approve_suggestions(modeladmin, request, queryset):
    for s in queryset.filter(status="pending"):
        s.approve(reviewer=request.user.get_username())


@admin.action(description="Reject")
def reject_suggestions(modeladmin, request, queryset):
    queryset.update(status="rejected", reviewed_by=request.user.get_username())


@admin.register(FAQSuggestion)
class FAQSuggestionAdmin(admin.ModelAdmin):
    list_display = ("question", "status", "reviewed_by", "created_at")
    list_filter = ("status",)
    search_fields = ("question", "answer")
    actions = [approve_suggestions, reject_suggestions]