"""Route-level tests for the skill marketplace API module."""

import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch


def _load_skill_marketplace_module_from_source():
    module_name = "_skill_marketplace_api_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "api"
        / "v1"
        / "skill_marketplace.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


def test_skill_marketplace_module_import_does_not_initialize_storage_service() -> None:
    with patch(
        "app.services.storage_service.S3StorageService",
        side_effect=AssertionError("storage should be lazy"),
    ):
        module = _load_skill_marketplace_module_from_source()

    assert module.discover_skills_marketplace_import is not None
