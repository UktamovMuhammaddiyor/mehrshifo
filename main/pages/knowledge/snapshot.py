import hashlib

from django.core.cache import cache
from django.db.models.signals import post_save, post_delete

KB_CACHE_KEY = "kb_snapshot_v1"


def build_kb_snapshot() -> str:
    from ..models import Service, Doctor, ClinicInfo, FAQ
    parts = []

    info = ClinicInfo.get()
    if info:
        parts.append("== KLINIKA ==")
        parts.append(f"Nomi: {info.name}")
        if info.address:
            parts.append(f"Manzil: {info.address}")
        if info.phones:
            parts.append(f"Telefon: {info.phones}")
        if info.working_hours:
            parts.append(f"Ish vaqti: {info.working_hours}")
        if info.days_off:
            parts.append(f"Dam olish kunlari: {info.days_off}")
        if info.extra_notes:
            parts.append(info.extra_notes)

    services = Service.objects.filter(is_active=True).order_by("category", "name")
    if services:
        parts.append("\n== XIZMATLAR VA NARXLAR ==")
        for s in services:
            price = f"{s.price} {s.currency}" if s.price is not None else "narx so'rov bo'yicha"
            dur = f", {s.duration_min} daqiqa" if s.duration_min else ""
            desc = f" — {s.description}" if s.description else ""
            parts.append(f"- {s.name}: {price}{dur}{desc}")

    doctors = Doctor.objects.filter(is_active=True).order_by("full_name")
    if doctors:
        parts.append("\n== SHIFOKORLAR ==")
        for d in doctors:
            sched = f", qabul: {d.schedule_text}" if d.schedule_text else ""
            parts.append(f"- {d.full_name} ({d.specialty}){sched}")

    faqs = FAQ.objects.filter(is_active=True)
    if faqs:
        parts.append("\n== TEZ-TEZ BERILADIGAN SAVOLLAR ==")
        for f in faqs:
            parts.append(f"S: {f.question}\nJ: {f.answer}")

    return "\n".join(parts).strip() or "(Bilim bazasi hozircha bo'sh.)"


def get_kb_snapshot() -> str:
    snap = cache.get(KB_CACHE_KEY)
    if snap is None:
        snap = build_kb_snapshot()
        cache.set(KB_CACHE_KEY, snap, None)  # no TTL; invalidated explicitly on save
    return snap


def kb_version(snapshot: str | None = None) -> str:
    snap = snapshot if snapshot is not None else get_kb_snapshot()
    return hashlib.md5(snap.encode("utf-8")).hexdigest()[:8]


def _invalidate(**kwargs):
    cache.delete(KB_CACHE_KEY)


def connect_signals():
    from ..models import Service, Doctor, ClinicInfo, FAQ
    for model in (Service, Doctor, ClinicInfo, FAQ):
        post_save.connect(_invalidate, sender=model, dispatch_uid=f"kb_save_{model.__name__}")
        post_delete.connect(_invalidate, sender=model, dispatch_uid=f"kb_del_{model.__name__}")
