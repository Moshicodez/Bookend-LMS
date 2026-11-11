import re
import unittest
from pathlib import Path


class ConfirmationFormTests(unittest.TestCase):
    def test_destructive_template_forms_have_confirmation_copy(self):
        template_root = Path(__file__).parents[1] / "frontend" / "templates"
        opening_form = re.compile(r"<form\b([^>]*)>(.*?)</form>", re.IGNORECASE | re.DOTALL)
        route_name = re.compile(r"url_for\(['\"]([^'\"]+)", re.IGNORECASE)
        text_tags = re.compile(r"<[^>]+>")
        destructive_words = re.compile(r"\b(delete|remove|clear|void)\b", re.IGNORECASE)
        failures = []

        for path in template_root.rglob("*.html"):
            if path.name == "confirm_action.html":
                continue
            source = path.read_text(encoding="utf-8")
            for attributes, body in opening_form.findall(source):
                route = route_name.search(attributes)
                route_is_destructive = bool(
                    route
                    and re.search(
                        r"(delete|remove|clear|void|import_backup)",
                        route.group(1),
                        re.IGNORECASE,
                    )
                )
                visible_copy = text_tags.sub(" ", body)
                if route_is_destructive or destructive_words.search(visible_copy):
                    if not all(
                        attribute in attributes
                        for attribute in (
                            "data-confirm-title",
                            "data-confirm-message",
                            "data-confirm-action",
                        )
                    ):
                        failures.append(f"{path}: {attributes.strip()}")

        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
