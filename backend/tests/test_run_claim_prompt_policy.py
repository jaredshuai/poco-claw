import unittest

from app.services.run_claim_prompt_policy import RunClaimPromptPolicy


class TestRunClaimPromptPolicy(unittest.TestCase):
    """Test run claim prompt extraction policy."""

    def test_extracts_first_text_block_when_type_contains_text_block(self) -> None:
        prompt = RunClaimPromptPolicy.extract_prompt(
            {
                "content": [
                    {"_type": "OtherBlock", "text": "skip"},
                    {"_type": "anthropic.types.TextBlock", "text": "Use this prompt"},
                    {"_type": "TextBlock", "text": "Do not reach this"},
                ]
            },
            text_preview="fallback",
        )

        self.assertEqual(prompt, "Use this prompt")

    def test_uses_text_preview_when_structured_content_has_no_text(self) -> None:
        prompt = RunClaimPromptPolicy.extract_prompt(
            {
                "content": [
                    "not a block",
                    {"_type": "OtherBlock", "text": "skip"},
                    {"_type": "TextBlock", "text": 123},
                ]
            },
            text_preview="Fallback prompt",
        )

        self.assertEqual(prompt, "Fallback prompt")

    def test_returns_none_when_no_prompt_can_be_extracted(self) -> None:
        prompt = RunClaimPromptPolicy.extract_prompt(
            {"content": [{"_type": "TextBlock", "text": 123}]},
            text_preview=None,
        )

        self.assertIsNone(prompt)

    def test_returns_none_for_empty_text_preview(self) -> None:
        prompt = RunClaimPromptPolicy.extract_prompt(
            {"content": [{"_type": "OtherBlock", "text": "skip"}]},
            text_preview="",
        )

        self.assertIsNone(prompt)


if __name__ == "__main__":
    unittest.main()
