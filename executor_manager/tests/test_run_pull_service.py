"""Tests for run_pull_service.py."""

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.run_pull_service as run_pull_module
from app.services.run_dispatch_config_preparer import (
    _extract_enabled_skill_names,
)
from app.services.run_pull_service import RunPullService
from app.services.run_dispatch_claim import RunDispatchClaim


def make_run_dispatch_claim(
    *,
    run_id: object = "run-1",
    session_id: str = "sess-1",
    user_id: str = "user-1",
    prompt: str = "test",
    config_snapshot: dict | None = None,
) -> RunDispatchClaim:
    return RunDispatchClaim(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        prompt=prompt,
        config_snapshot=config_snapshot or {},
    )


class TestExtractEnabledSkillNames(unittest.TestCase):
    """Test _extract_enabled_skill_names pure function."""

    def test_empty_dict(self) -> None:
        """Test with empty dict."""
        result = _extract_enabled_skill_names({})
        assert result == []

    def test_none_input(self) -> None:
        """Test with None input."""
        result = _extract_enabled_skill_names(None)
        assert result == []

    def test_list_input(self) -> None:
        """Test with list input (not dict)."""
        result = _extract_enabled_skill_names(["skill1", "skill2"])
        assert result == []

    def test_simple_skills(self) -> None:
        """Test with simple enabled skills."""
        result = _extract_enabled_skill_names(
            {
                "skill1": {},
                "skill2": {"enabled": True},
            }
        )
        assert result == ["skill1", "skill2"]

    def test_disabled_skill_excluded(self) -> None:
        """Test that disabled skills are excluded."""
        result = _extract_enabled_skill_names(
            {
                "skill1": {},
                "skill2": {"enabled": False},
            }
        )
        assert result == ["skill1"]

    def test_empty_name_skipped(self) -> None:
        """Test that empty names are skipped."""
        result = _extract_enabled_skill_names(
            {
                "skill1": {},
                "": {},
                "  ": {},
            }
        )
        assert result == ["skill1"]

    def test_non_string_name_skipped(self) -> None:
        """Test that non-string names are skipped."""
        result = _extract_enabled_skill_names(
            {
                "skill1": {},
                123: {},  # type: ignore
                None: {},  # type: ignore
            }
        )
        assert result == ["skill1"]

    def test_whitespace_trimmed(self) -> None:
        """Test that names are trimmed."""
        result = _extract_enabled_skill_names(
            {
                "  skill1  ": {},
                "skill2": {},
            }
        )
        assert "skill1" in result
        assert "skill2" in result

    def test_returns_sorted(self) -> None:
        """Test that result is sorted."""
        result = _extract_enabled_skill_names(
            {
                "zebra": {},
                "alpha": {},
                "beta": {},
            }
        )
        assert result == ["alpha", "beta", "zebra"]

    def test_deduplication(self) -> None:
        """Test that duplicate names are deduplicated."""
        result = _extract_enabled_skill_names(
            {
                "skill1": {},
                "  skill1  ": {},  # Same after trim
            }
        )
        assert result == ["skill1"]


class TestRunPullServiceDependencies(unittest.TestCase):
    """Test RunPullService dependency injection."""

    def test_public_exports_stay_at_pull_boundary(self) -> None:
        assert run_pull_module.__all__ == [
            "RunPullService",
            "RunPullDispatchService",
            "RunPullBackendClientPort",
        ]

    def test_run_pull_service_settings_is_named_protocol_not_any(self) -> None:
        """Regression test: RunPullServiceSettings should be a named Protocol, not Any."""
        from typing import Protocol, get_type_hints

        from app.services.run_pull_service import RunPullServiceSettings

        # RunPullServiceSettings should be a Protocol class
        assert issubclass(RunPullServiceSettings, Protocol)

        # It should have the expected attributes
        hints = get_type_hints(RunPullServiceSettings)
        assert "max_concurrent_tasks" in hints
        assert "task_claim_lease_seconds" in hints

    def test_run_pull_service_init_settings_annotation_not_any(self) -> None:
        """Regression test: RunPullService.__init__.settings should not be Any."""
        import inspect
        from typing import Any

        sig = inspect.signature(RunPullService.__init__)
        settings_param = sig.parameters["settings"]
        settings_annotation = settings_param.annotation

        assert settings_annotation is not Any
        hint_str = str(settings_annotation)
        assert "Any" not in hint_str
        assert "RunPullServiceSettings" in hint_str

    def test_build_run_pull_dispatch_service_settings_annotation_not_any(self) -> None:
        """Regression test: build_run_pull_dispatch_service.settings should not be Any."""
        import inspect
        from typing import Any

        from app.services.run_pull_service import build_run_pull_dispatch_service

        sig = inspect.signature(build_run_pull_dispatch_service)
        settings_param = sig.parameters["settings"]
        settings_annotation = settings_param.annotation

        # The annotation should not be Any
        assert settings_annotation is not Any
        hint_str = str(settings_annotation)
        assert "RunPullServiceSettings" in hint_str

    def test_dispatch_service_factory_settings_annotation_not_any(self) -> None:
        """Regression test: dispatch_service_factory callback settings arg should not be Any."""
        import inspect

        sig = inspect.signature(RunPullService.__init__)
        factory_param = sig.parameters["dispatch_service_factory"]
        factory_annotation = factory_param.annotation

        hint_str = str(factory_annotation)
        assert "Any" not in hint_str
        assert "RunPullServiceSettings" in hint_str

    def test_constructor_rejects_dispatch_adapter_dependencies(self) -> None:
        """Dispatch adapters belong behind RunDispatchService, not RunPullService."""
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )
        backend_client = MagicMock()
        executor_client = MagicMock()

        with self.assertRaises(TypeError):
            RunPullService(
                settings=settings,
                backend_client=backend_client,
                executor_client=executor_client,
            )

    def test_service_does_not_expose_dispatch_adapter_proxies(self) -> None:
        adapter_names = [
            "backend_client",
            "executor_client",
            "container_pool",
            "config_resolver",
            "skill_stager",
            "plugin_stager",
            "attachment_stager",
            "claude_md_stager",
            "slash_command_stager",
            "subagent_stager",
        ]

        for name in adapter_names:
            assert not hasattr(RunPullService, name)

    def test_handle_claim_delegates_to_injected_dispatch_service(self) -> None:
        """RunPullService should not need dispatch adapters when a use case is injected."""
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )
        backend_client = MagicMock()
        dispatch_service = MagicMock()
        dispatch_service.dispatch_claim = AsyncMock()
        claim = make_run_dispatch_claim(prompt="test prompt")

        service = RunPullService(
            settings=settings,
            backend_client=backend_client,
            dispatch_service=dispatch_service,
        )

        asyncio.run(service._handle_claim(claim))

        dispatch_service.dispatch_claim.assert_awaited_once()
        dispatch_claim = dispatch_service.dispatch_claim.call_args.args[0]
        assert isinstance(dispatch_claim, RunDispatchClaim)
        assert dispatch_claim.run_id == "run-1"
        assert dispatch_claim.session_id == "sess-1"
        assert dispatch_claim.user_id == "user-1"
        assert dispatch_claim.prompt == "test prompt"
        dispatch_service.dispatch_claim.assert_awaited_once_with(
            dispatch_claim,
            worker_id=service.worker_id,
        )

    def test_handle_claim_rejects_raw_backend_payloads(self) -> None:
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
        )
        dispatch_service = MagicMock()
        dispatch_service.dispatch_claim = AsyncMock()
        service = RunPullService(
            settings=settings,
            dispatch_service=dispatch_service,
        )

        with self.assertRaises(TypeError):
            asyncio.run(
                service._handle_claim(
                    {
                        "run": {"run_id": "run-1", "session_id": "sess-1"},
                        "user_id": "user-1",
                        "prompt": "test",
                    }
                )
            )

        dispatch_service.dispatch_claim.assert_not_called()

    def test_constructor_defers_default_backend_client(self) -> None:
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )

        with patch(
            "app.services.run_pull_service.BackendClient",
            side_effect=AssertionError("backend client should be lazy"),
        ):
            service = RunPullService(settings=settings)

        assert service.settings is settings

    def test_constructor_builds_dispatch_service_boundary_lazily_by_default(
        self,
    ) -> None:
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )
        backend_client = MagicMock()

        with patch("app.services.run_pull_service.RunDispatchService") as dispatch_cls:
            dispatch_service = MagicMock()
            dispatch_cls.create_default.return_value = dispatch_service

            service = RunPullService(
                settings=settings,
                backend_client=backend_client,
            )
            dispatch_cls.create_default.assert_not_called()

            assert service.dispatch_service is dispatch_service
            dispatch_cls.create_default.assert_called_once_with(
                settings=settings,
                backend_client=backend_client,
            )

    def test_constructor_uses_injected_dispatch_service_factory_lazily(
        self,
    ) -> None:
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )
        backend_client = MagicMock()
        dispatch_service = MagicMock()
        dispatch_service_factory = MagicMock(return_value=dispatch_service)

        with patch(
            "app.services.run_pull_service.RunDispatchService.create_default",
            side_effect=AssertionError("dispatch service should be injected"),
        ):
            service = RunPullService(
                settings=settings,
                backend_client=backend_client,
                dispatch_service_factory=dispatch_service_factory,
            )
            dispatch_service_factory.assert_not_called()

            assert service.dispatch_service is dispatch_service

        dispatch_service_factory.assert_called_once_with(settings, backend_client)

    def test_constructor_uses_injected_backend_factory_without_constructing_default(
        self,
    ) -> None:
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )
        backend_client = MagicMock()
        dispatch_service = MagicMock()
        queue_gateway = MagicMock()
        queue_gateway_factory = MagicMock(return_value=queue_gateway)

        with patch(
            "app.services.run_pull_service.BackendClient",
            side_effect=AssertionError("backend client should be provided by factory"),
        ):
            service = RunPullService(
                settings=settings,
                backend_client_factory=lambda: backend_client,
                dispatch_service=dispatch_service,
                queue_gateway_factory=queue_gateway_factory,
            )

        assert service.dispatch_service is dispatch_service
        assert service.queue_gateway is queue_gateway
        queue_gateway_factory.assert_called_once_with(backend_client)

    def test_poll_uses_injected_queue_gateway(self) -> None:
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )
        backend_client = MagicMock()
        backend_client.claim_run = AsyncMock(
            side_effect=AssertionError("poll should claim through queue gateway")
        )
        queue_gateway = MagicMock()
        queue_gateway.claim_run = AsyncMock(return_value=None)

        service = RunPullService(
            settings=settings,
            backend_client=backend_client,
            dispatch_service=MagicMock(),
            queue_gateway=queue_gateway,
        )

        asyncio.run(service.poll(schedule_modes=["manual"]))

        queue_gateway.claim_run.assert_awaited_once_with(
            worker_id=service.worker_id,
            lease_seconds=30,
            schedule_modes=["manual"],
        )
        backend_client.claim_run.assert_not_called()

    def test_constructor_uses_injected_settings_without_loading_global_settings(
        self,
    ) -> None:
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )
        settings.__bool__.return_value = False
        backend_client = MagicMock()
        dispatch_service = MagicMock()

        with patch(
            "app.services.run_pull_service.get_settings",
            side_effect=AssertionError("settings should be injected"),
        ):
            service = RunPullService(
                settings=settings,
                backend_client=backend_client,
                dispatch_service=dispatch_service,
            )

        assert service.settings is settings


class TestGetWindowLock(unittest.TestCase):
    """Test RunPullService._get_window_lock."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_creates_new_lock(self) -> None:
        """Test creating a new lock for a window."""
        service = self._create_service()
        lock = service._get_window_lock("window-1")

        assert isinstance(lock, asyncio.Lock)
        assert "window-1" in service._window_locks

    def test_returns_existing_lock(self) -> None:
        """Test returning existing lock."""
        service = self._create_service()
        lock1 = service._get_window_lock("window-1")
        lock2 = service._get_window_lock("window-1")

        assert lock1 is lock2

    def test_different_windows_different_locks(self) -> None:
        """Test different windows get different locks."""
        service = self._create_service()
        lock1 = service._get_window_lock("window-1")
        lock2 = service._get_window_lock("window-2")

        assert lock1 is not lock2


class TestSetWindowUntil(unittest.TestCase):
    """Test RunPullService.set_window_until."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_sets_window_until(self) -> None:
        """Test setting window until time."""
        service = self._create_service()
        until = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        service.set_window_until("window-1", until)

        assert service._windows_until["window-1"] == until

    def test_empty_window_id_ignored(self) -> None:
        """Test empty window_id is ignored."""
        service = self._create_service()
        until = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        service.set_window_until("", until)
        service.set_window_until("   ", until)

        assert service._windows_until == {}

    def test_naive_datetime_gets_utc(self) -> None:
        """Test naive datetime gets UTC timezone."""
        service = self._create_service()
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)  # No timezone

        service.set_window_until("window-1", naive_dt)

        result = service._windows_until["window-1"]
        assert result.tzinfo == timezone.utc


class TestRegisterInflightRun(unittest.TestCase):
    """Test RunPullService._register_inflight_run."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_registers_new_run(self) -> None:
        """Test registering a new run."""
        service = self._create_service()

        result = asyncio.run(service._register_inflight_run("run-1"))

        assert result is True
        assert "run-1" in service._inflight_run_ids

    def test_duplicate_run_returns_false(self) -> None:
        """Test duplicate run returns False."""
        service = self._create_service()

        asyncio.run(service._register_inflight_run("run-1"))
        result = asyncio.run(service._register_inflight_run("run-1"))

        assert result is False


class TestReleaseInflightRun(unittest.TestCase):
    """Test RunPullService._release_inflight_run."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_releases_run(self) -> None:
        """Test releasing a run."""
        service = self._create_service()
        asyncio.run(service._register_inflight_run("run-1"))

        asyncio.run(service._release_inflight_run("run-1"))

        assert "run-1" not in service._inflight_run_ids

    def test_release_nonexistent_run_safe(self) -> None:
        """Test releasing nonexistent run is safe."""
        service = self._create_service()

        # Should not raise
        asyncio.run(service._release_inflight_run("nonexistent"))


class TestOpenWindow(unittest.TestCase):
    """Test RunPullService.open_window."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            service = RunPullService()
            service.poll = AsyncMock()  # Mock poll to avoid backend calls
            return service

    def test_open_window_when_shutdown(self) -> None:
        """Test open_window returns early when shutdown."""
        service = self._create_service()
        service._shutdown = True

        asyncio.run(service.open_window("window-1"))

        assert service.poll.called is False

    def test_open_window_empty_id(self) -> None:
        """Test open_window with empty window_id."""
        service = self._create_service()

        asyncio.run(service.open_window(""))

        assert service.poll.called is False

    def test_open_window_sets_until_time(self) -> None:
        """Test open_window sets until time."""
        service = self._create_service()

        asyncio.run(service.open_window("window-1", window_minutes=30))

        assert "window-1" in service._windows_until
        assert service.poll.called is True

    def test_open_window_uses_injected_clock(self) -> None:
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
        )
        fixed_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        clock = MagicMock()
        clock.now_utc.return_value = fixed_now
        service = RunPullService(
            settings=settings,
            backend_client=MagicMock(),
            dispatch_service=MagicMock(),
            clock=clock,
        )
        service.poll = AsyncMock()

        asyncio.run(service.open_window("window-1", window_minutes=30))

        assert service._windows_until["window-1"] == fixed_now + timedelta(minutes=30)
        clock.now_utc.assert_called_once_with()

    def test_open_window_negative_minutes_defaults(self) -> None:
        """Test open_window with negative minutes defaults to 60."""
        service = self._create_service()

        asyncio.run(service.open_window("window-1", window_minutes=-10))

        assert "window-1" in service._windows_until
        assert service.poll.called is True


class TestPollWindow(unittest.TestCase):
    """Test RunPullService.poll_window."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            service = RunPullService()
            service.poll = AsyncMock()
            return service

    def test_poll_window_when_shutdown(self) -> None:
        """Test poll_window returns early when shutdown."""
        service = self._create_service()
        service._shutdown = True

        asyncio.run(service.poll_window("window-1"))

        assert service.poll.called is False

    def test_poll_window_empty_id(self) -> None:
        """Test poll_window with empty window_id."""
        service = self._create_service()

        asyncio.run(service.poll_window(""))

        assert service.poll.called is False

    def test_poll_window_no_until_set(self) -> None:
        """Test poll_window when no until time set."""
        service = self._create_service()

        asyncio.run(service.poll_window("window-1"))

        assert service.poll.called is False

    def test_poll_window_uses_injected_clock_for_expiry(self) -> None:
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
        )
        fixed_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        clock = MagicMock()
        clock.now_utc.return_value = fixed_now
        service = RunPullService(
            settings=settings,
            backend_client=MagicMock(),
            dispatch_service=MagicMock(),
            clock=clock,
        )
        service.poll = AsyncMock()
        service.set_window_until("window-1", fixed_now - timedelta(seconds=1))

        asyncio.run(service.poll_window("window-1"))

        assert "window-1" not in service._windows_until
        assert service.poll.called is False
        clock.now_utc.assert_called_once_with()

    def test_poll_window_expired(self) -> None:
        """Test poll_window when window has expired."""
        service = self._create_service()
        service._windows_until["window-1"] = datetime(
            2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc
        )

        asyncio.run(service.poll_window("window-1"))

        assert service.poll.called is False
        assert "window-1" not in service._windows_until

    def test_poll_window_active(self) -> None:
        """Test poll_window with active window."""
        service = self._create_service()
        service._windows_until["window-1"] = datetime.now(timezone.utc) + timedelta(
            hours=1
        )

        asyncio.run(service.poll_window("window-1"))

        assert service.poll.called is True


class TestShutdown(unittest.TestCase):
    """Test RunPullService.shutdown."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_shutdown_sets_flag(self) -> None:
        """Test shutdown sets shutdown flag."""
        service = self._create_service()

        asyncio.run(service.shutdown())

        assert service._shutdown is True

    def test_shutdown_clears_tasks(self) -> None:
        """Test shutdown clears tasks."""
        service = self._create_service()

        asyncio.run(service.shutdown())

        assert service._tasks == set()


class TestPoll(unittest.TestCase):
    """Test RunPullService.poll."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )
        queue_gateway = MagicMock()
        queue_gateway.claim_run = AsyncMock()
        dispatch_service = MagicMock()
        dispatch_service.dispatch_claim = AsyncMock()
        return RunPullService(
            settings=settings,
            queue_gateway=queue_gateway,
            dispatch_service=dispatch_service,
        )

    def test_poll_when_shutdown(self) -> None:
        """Test poll returns early when shutdown."""
        service = self._create_service()
        service._shutdown = True

        asyncio.run(service.poll())

        assert service.queue_gateway.claim_run.called is False

    def test_poll_no_claim(self) -> None:
        """Test poll when no run to claim."""
        service = self._create_service()
        service.queue_gateway.claim_run = AsyncMock(return_value=None)

        asyncio.run(service.poll())

        service.queue_gateway.claim_run.assert_called_once()

    def test_poll_claim_exception(self) -> None:
        """Test poll handles claim exception."""
        service = self._create_service()
        service.queue_gateway.claim_run = AsyncMock(
            side_effect=Exception("Backend error")
        )

        asyncio.run(service.poll())

        # Should not raise, just log error
        service.queue_gateway.claim_run.assert_called_once()


class TestOnTaskDone(unittest.TestCase):
    """Test RunPullService._on_task_done."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_on_task_done_removes_task(self) -> None:
        """Test _on_task_done removes task from set."""

        async def run_test() -> None:
            service = self._create_service()

            async def dummy_task() -> None:
                pass

            task = asyncio.create_task(dummy_task())
            service._tasks.add(task)

            await task  # Complete the task
            service._on_task_done(task)

            assert task not in service._tasks

        asyncio.run(run_test())

    def test_on_task_done_releases_semaphore(self) -> None:
        """Test _on_task_done releases semaphore."""

        async def run_test() -> None:
            service = self._create_service()

            async def dummy_task() -> None:
                pass

            task = asyncio.create_task(dummy_task())
            await service._semaphore.acquire()  # Lock semaphore

            await task
            service._on_task_done(task)

            # Semaphore should be released
            assert not service._semaphore.locked()

        asyncio.run(run_test())


class TestDrainTasks(unittest.TestCase):
    """Test RunPullService._drain_tasks."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_drain_tasks_empty(self) -> None:
        """Test _drain_tasks with no tasks."""
        service = self._create_service()

        asyncio.run(service._drain_tasks())

        assert service._tasks == set()

    def test_drain_tasks_cancels_tasks(self) -> None:
        """Test _drain_tasks cancels and clears tasks."""

        async def run_test() -> None:
            service = self._create_service()

            async def long_task() -> None:
                await asyncio.sleep(10)

            task1 = asyncio.create_task(long_task())
            task2 = asyncio.create_task(long_task())
            service._tasks.add(task1)
            service._tasks.add(task2)

            await service._drain_tasks()

            assert service._tasks == set()
            assert task1.cancelled()
            assert task2.cancelled()

        asyncio.run(run_test())


class TestPollWithClaim(unittest.TestCase):
    """Test RunPullService.poll with successful claim."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        settings = MagicMock(
            max_concurrent_tasks=5,
            task_claim_lease_seconds=30,
            callback_base_url="http://test.local",
            callback_token="test-token",
        )
        queue_gateway = MagicMock()
        queue_gateway.claim_run = AsyncMock(
            return_value=make_run_dispatch_claim(prompt="test prompt")
        )
        dispatch_service = MagicMock()
        dispatch_service.dispatch_claim = AsyncMock()
        return RunPullService(
            settings=settings,
            queue_gateway=queue_gateway,
            dispatch_service=dispatch_service,
        )

    def test_poll_creates_task_on_claim(self) -> None:
        """Test poll creates task when claim succeeds."""
        service = self._create_service()

        # Run poll but cancel after task is created
        async def run_poll() -> None:
            task = asyncio.create_task(service.poll())
            # Wait for claim to be processed
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_poll())

        # Verify claim was called
        service.queue_gateway.claim_run.assert_called()


class TestHandleClaimDuplicateRun(unittest.TestCase):
    """Test RunPullService._handle_claim duplicate run detection."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_duplicate_run_skipped(self) -> None:
        """Test that duplicate run is skipped."""
        service = self._create_service()
        claim = make_run_dispatch_claim()

        # Register run first
        asyncio.run(service._register_inflight_run("run-1"))

        # Handle claim should skip duplicate
        asyncio.run(service._handle_claim(claim))

        # Should still only have one entry
        assert "run-1" in service._inflight_run_ids


class TestPollCancelledError(unittest.TestCase):
    """Test RunPullService.poll CancelledError handling (lines 178-179)."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=1,  # Set to 1 so semaphore locks after one acquire
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_poll_cancelled_error_releases_semaphore(self) -> None:
        """Test poll handles CancelledError and releases semaphore."""

        async def run_test() -> None:
            service = self._create_service()
            service.queue_gateway.claim_run = AsyncMock(
                side_effect=asyncio.CancelledError
            )

            # With max_concurrent_tasks=1, semaphore should be locked initially
            # poll() acquires semaphore first, then calls claim_run
            # If claim_run raises CancelledError, poll should release semaphore
            await service.poll()

            # Semaphore should be released after CancelledError
            # (poll acquires and releases on CancelledError)
            assert not service._semaphore.locked()

        asyncio.run(run_test())


class TestOnTaskDoneExceptionHandling(unittest.TestCase):
    """Test RunPullService._on_task_done exception handling (lines 207-208, 210)."""

    def _create_service(self) -> RunPullService:
        """Create service with mocked dependencies."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="http://test.local",
                callback_token="test-token",
            )
            return RunPullService()

    def test_on_task_done_with_exception(self) -> None:
        """Test _on_task_done logs when task has exception (line 210)."""

        async def run_test() -> None:
            service = self._create_service()

            async def failing_task() -> None:
                raise RuntimeError("Task failed")

            task = asyncio.create_task(failing_task())
            service._tasks.add(task)
            await service._semaphore.acquire()

            # Wait for task to complete
            try:
                await task
            except RuntimeError:
                pass

            # _on_task_done should handle the exception
            service._on_task_done(task)

            assert task not in service._tasks
            assert not service._semaphore.locked()

        asyncio.run(run_test())

    def test_on_task_done_cancelled_task(self) -> None:
        """Test _on_task_done handles CancelledError (lines 207-208)."""

        async def run_test() -> None:
            service = self._create_service()

            async def cancelled_task() -> None:
                await asyncio.sleep(10)

            task = asyncio.create_task(cancelled_task())
            service._tasks.add(task)
            await service._semaphore.acquire()

            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # _on_task_done should handle CancelledError from task.exception()
            service._on_task_done(task)

            assert task not in service._tasks

        asyncio.run(run_test())


class TestHandleClaimEmptyCallbackUrl(unittest.TestCase):
    """Test RunPullService._handle_claim with empty callback_base_url (line 255)."""

    def _create_service_with_empty_callback(self) -> RunPullService:
        """Create service with empty callback_base_url."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url="",  # Empty callback URL
                callback_token="test-token",
            )
            return RunPullService()

    def test_handle_claim_empty_callback_url_raises(self) -> None:
        """Test _handle_claim raises ValueError when callback_base_url is empty."""

        async def run_test() -> None:
            service = self._create_service_with_empty_callback()
            claim = make_run_dispatch_claim()

            # Should raise ValueError for empty callback_base_url
            with self.assertRaises(ValueError) as ctx:
                await service._handle_claim(claim)

            assert "callback_base_url cannot be empty" in str(ctx.exception)
            # Run should be released from inflight set in finally block
            # (exception happens in try block, finally releases the run)

        asyncio.run(run_test())

    def test_handle_claim_none_callback_url_raises(self) -> None:
        """Test _handle_claim raises ValueError when callback_base_url is None."""
        with (
            patch("app.services.run_pull_service.get_settings") as mock_settings,
            patch("app.services.run_pull_service.BackendClient"),
            patch("app.services.run_dispatch_service.ExecutorClient"),
            patch("app.services.run_dispatch_service.ConfigResolver"),
            patch("app.services.run_dispatch_service.SkillStager"),
            patch("app.services.run_dispatch_service.PluginStager"),
            patch("app.services.run_dispatch_service.AttachmentStager"),
            patch("app.services.run_dispatch_service.ClaudeMdStager"),
            patch("app.services.run_dispatch_service.SlashCommandStager"),
            patch("app.services.run_dispatch_service.SubAgentStager"),
        ):
            mock_settings.return_value = MagicMock(
                max_concurrent_tasks=5,
                task_claim_lease_seconds=30,
                callback_base_url=None,  # None callback URL
                callback_token="test-token",
            )
            service = RunPullService()

            async def run_test() -> None:
                claim = make_run_dispatch_claim()

                with self.assertRaises(ValueError) as ctx:
                    await service._handle_claim(claim)

                assert "callback_base_url cannot be empty" in str(ctx.exception)

            asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
