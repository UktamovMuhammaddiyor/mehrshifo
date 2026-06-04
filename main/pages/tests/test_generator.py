from unittest import mock
from django.test import SimpleTestCase
from pages.publishing import generator


class GeneratorTests(SimpleTestCase):
    @mock.patch("pages.publishing.generator._openai_web_search")
    def test_builds_prompt_and_returns_body(self, search):
        search.return_value = "Yaratilgan maqola matni"
        out = generator.generate_content(
            kind="article", title="Kardiologiya", reference_link="https://x/y",
            kb_snapshot="KB_MARKER",
        )
        self.assertEqual(out["title"], "Kardiologiya")
        self.assertEqual(out["body"], "Yaratilgan maqola matni")
        prompt = search.call_args.args[0]
        self.assertIn("Kardiologiya", prompt)
        self.assertIn("KB_MARKER", prompt)
        self.assertIn("https://x/y", prompt)

    @mock.patch("pages.publishing.generator._openai_web_search")
    def test_post_kind_uses_short_style(self, search):
        search.return_value = "qisqa post"
        generator.generate_content(kind="post", title="Aksiya", reference_link="", kb_snapshot="")
        self.assertIn("post", search.call_args.args[0].lower())
