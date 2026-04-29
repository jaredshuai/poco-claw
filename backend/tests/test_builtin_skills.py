import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lifecycle.builtin_skills import BUILTIN_SKILLS, SkillBootstrapService


class BuiltinOfficeSkillsTests(unittest.TestCase):
    def test_office_skills_are_registered(self) -> None:
        registered_names = {definition.name for definition in BUILTIN_SKILLS}

        self.assertTrue(
            {
                "office-assistant",
                "docx",
                "xlsx",
                "pdf",
                "pptx",
            }.issubset(registered_names)
        )

    def test_registered_builtin_skills_have_markdown_assets(self) -> None:
        for definition in BUILTIN_SKILLS:
            with self.subTest(skill=definition.name):
                self.assertTrue(definition.asset_dir.is_dir())
                self.assertTrue((definition.asset_dir / "SKILL.md").is_file())
                bundle = SkillBootstrapService._build_bundle(definition)
                self.assertEqual(bundle.definition.name, definition.name)
                self.assertTrue(bundle.description)

    def test_storage_uses_injected_factory_without_constructing_s3(self) -> None:
        storage_service = MagicMock()

        with patch(
            "app.lifecycle.builtin_skills.S3StorageService",
            side_effect=AssertionError("storage should be provided by factory"),
        ):
            result = SkillBootstrapService._build_storage_service(
                storage_service_factory=lambda: storage_service,
            )

        self.assertIs(result, storage_service)


if __name__ == "__main__":
    unittest.main()
