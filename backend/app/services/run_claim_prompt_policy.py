class RunClaimPromptPolicy:
    """Policy for selecting the prompt payload returned when a worker claims a run."""

    @staticmethod
    def extract_prompt(
        message_content: object,
        text_preview: str | None,
    ) -> str | None:
        prompt = RunClaimPromptPolicy._extract_text_block(message_content)
        if prompt:
            return prompt
        return text_preview or None

    @staticmethod
    def _extract_text_block(message_content: object) -> str | None:
        if not isinstance(message_content, dict):
            return None

        content_blocks = message_content.get("content")
        if not isinstance(content_blocks, list):
            return None

        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            if "TextBlock" in str(block.get("_type", "")) and isinstance(
                block.get("text"), str
            ):
                return block["text"]
        return None
