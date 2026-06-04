from django.db import models

# Create your models here.
class BotUser(models.Model):
    name = models.CharField(max_length=255)
    user_id = models.BigIntegerField()
    user_name = models.CharField(max_length=255)
    is_admin = models.BooleanField(default=False)
    status = models.CharField(max_length=255, default="")
    is_subcribe = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class AboutMessage(models.Model):
    link = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    message_type = models.CharField(max_length=15, default="Message", blank=True)
    chat_id = models.BigIntegerField(blank=True)
    file_id = models.CharField(max_length=255, default=0, blank=True)
    message_id = models.IntegerField(default=0, blank=True)
    answer = models.CharField(max_length=255, default="", blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.link
    

class ChannelMessage(models.Model):
    message = models.TextField(blank=True)
    message_type = models.CharField(max_length=15, default="Message", blank=True)
    chat_id = models.BigIntegerField(default=0)
    file_id = models.CharField(max_length=255, default=0, blank=True)
    answer = models.CharField(max_length=255, default="", blank=True)

    def __str__(self) -> str:
        return f"{self.chat_id}"
    

class ChannelBot(models.Model):
    name = models.CharField(max_length=255)
    chat_link = models.CharField(max_length=255, blank=True)
    chat_id = models.BigIntegerField()

    def __str__(self) -> str:
        return self.name


class GroupBot(models.Model):
    name = models.CharField(max_length=255)
    group_link = models.CharField(max_length=255, blank=True)
    group_id = models.BigIntegerField()
    is_active = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class AutoAnswer(models.Model):
    text = models.TextField(default="")

    def __str__(self) -> str:
        return self.text[:20]


class Service(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, default="UZS")
    duration_min = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class Doctor(models.Model):
    full_name = models.CharField(max_length=255)
    specialty = models.CharField(max_length=255, blank=True)
    schedule_text = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.full_name


class ClinicInfo(models.Model):
    """Single-row clinic profile (one clinic, no branches)."""
    name = models.CharField(max_length=255, default="")
    address = models.CharField(max_length=512, blank=True)
    geo_lat = models.FloatField(null=True, blank=True)
    geo_long = models.FloatField(null=True, blank=True)
    phones = models.CharField(max_length=255, blank=True)
    working_hours = models.CharField(max_length=512, blank=True)
    days_off = models.CharField(max_length=255, blank=True)
    extra_notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name or "ClinicInfo"

    @classmethod
    def get(cls):
        return cls.objects.first()


class FAQ(models.Model):
    question = models.CharField(max_length=512)
    answer = models.TextField()
    category = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.question


class Conversation(models.Model):
    STATUS_CHOICES = [("active", "active"), ("handoff", "handoff"), ("closed", "closed")]
    user = models.ForeignKey(BotUser, on_delete=models.CASCADE, related_name="conversations")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    handoff_until = models.DateTimeField(null=True, blank=True)  # reserved; manual resume in P1
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user} [{self.status}]"

    @classmethod
    def active_for(cls, user):
        conv = (
            cls.objects.filter(user=user, status__in=["active", "handoff"])
            .order_by("-id")
            .first()
        )
        if conv is None:
            conv = cls.objects.create(user=user, status="active")
        return conv


class ConversationMessage(models.Model):
    ROLE_CHOICES = [("client", "client"), ("ai", "ai"), ("staff", "staff")]
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=8, choices=ROLE_CHOICES)
    text = models.TextField(blank=True)
    tg_message_id = models.BigIntegerField(null=True, blank=True)
    intent = models.CharField(max_length=64, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class AISettings(models.Model):
    """Single-row AI configuration."""
    is_enabled = models.BooleanField(default=False)
    model_name = models.CharField(max_length=64, default="gpt-4o")
    temperature = models.FloatField(default=0.3)
    confidence_threshold = models.FloatField(default=0.6)
    max_history_messages = models.PositiveIntegerField(default=12)
    max_input_chars = models.PositiveIntegerField(default=2000)
    max_output_tokens = models.PositiveIntegerField(default=500)
    daily_call_cap = models.PositiveIntegerField(default=1500)
    holding_message = models.TextField(
        default="Savolingiz mutaxassisimizga yuborildi. Tez orada javob beramiz. 🙏"
    )
    persona_extra = models.TextField(blank=True)
    complaint_notify_user_id = models.BigIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"AISettings (enabled={self.is_enabled})"

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class ProcessedUpdate(models.Model):
    update_id = models.BigIntegerField(unique=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.update_id)


class AIDecisionLog(models.Model):
    conversation = models.ForeignKey(
        Conversation, null=True, blank=True, on_delete=models.SET_NULL
    )
    input_text = models.TextField(blank=True)
    kb_version = models.CharField(max_length=64, blank=True)
    intent = models.CharField(max_length=64, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    action = models.CharField(max_length=16, blank=True)  # answer|notify|escalate|skipped
    output_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class ContentDraft(models.Model):
    KIND_CHOICES = [("post", "post"), ("article", "article")]
    MODE_CHOICES = [("ai", "ai"), ("manual", "manual")]
    STATUS_CHOICES = [
        ("draft", "draft"), ("generating", "generating"), ("ready", "ready"),
        ("published", "published"), ("failed", "failed"),
    ]
    created_by = models.ForeignKey(BotUser, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="post")
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="ai")
    title = models.CharField(max_length=512, blank=True)
    reference_link = models.URLField(blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")
    error = models.TextField(blank=True)
    targets = models.JSONField(default=dict, blank=True)
    publish_results = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"[{self.status}] {self.kind}: {self.title}"


class FAQSuggestion(models.Model):
    STATUS_CHOICES = [("pending", "pending"), ("approved", "approved"), ("rejected", "rejected")]
    question = models.CharField(max_length=512)
    answer = models.TextField()
    source_conversation = models.ForeignKey(
        "Conversation", null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    reviewed_by = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"[{self.status}] {self.question}"

    def approve(self, reviewer=""):
        """Create a real FAQ from this suggestion (idempotent) and mark approved."""
        faq, _ = FAQ.objects.get_or_create(
            question=self.question, defaults={"answer": self.answer}
        )
        self.status = "approved"
        self.reviewed_by = reviewer or None
        self.save(update_fields=["status", "reviewed_by"])
        return faq
