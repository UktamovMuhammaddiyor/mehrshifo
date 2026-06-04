def _build_prompt(kind, title, reference_link, kb_snapshot):
    style = (
        "qisqa, kanal uchun jozibali post (bir necha jumla, harakatga chaqiruv bilan)"
        if kind == "post"
        else "uzun, tuzilgan maqola (sarlavhalar va bo'limlar bilan)"
    )
    ref = f"Ushbu havoladagi maqolani ham o'qib, hisobga ol: {reference_link}\n" if reference_link else ""
    return (
        f"Sen klinikaning kontent-muharririsan. Klinika uchun {style} yoz.\n"
        f"Mavzu: {title}\n"
        f"{ref}"
        f"Internetdan ishonchli manbalarni qidir va shularga tayan.\n"
        f"Matnni klinikaga moslab yoz. Klinika ma'lumoti:\n{kb_snapshot}\n"
        f"O'zbek tilida yoz. Faqat tayyor kontent matnini qaytar (izohsiz)."
    )


def _openai_web_search(prompt, model="gpt-4o"):
    """Isolated OpenAI web-search call. Mocked in tests. Verify tool name vs current SDK."""
    from openai import OpenAI
    from ..creditionals import OPENAI_API_KEY
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.responses.create(
        model=model,
        tools=[{"type": "web_search"}],
        input=prompt,
    )
    return resp.output_text


def generate_content(kind, title, reference_link="", kb_snapshot="", model="gpt-4o"):
    prompt = _build_prompt(kind, title, reference_link, kb_snapshot)
    body = _openai_web_search(prompt, model=model)
    return {"title": title, "body": body}
