"""Tests for projects API Actor boundary integration."""

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any, TypeVar
from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.projects import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
from app.core.identity import Actor


T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine synchronously for testing."""
    return asyncio.run(coro)


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_project_service() -> MagicMock:
    service = MagicMock()
    service.list_projects = MagicMock()
    service.get_project = MagicMock()
    service.create_project = MagicMock()
    service.update_project = MagicMock()
    service.delete_project = MagicMock()
    return service


class TestListProjectsActorBoundary:
    """Tests for list_projects endpoint Actor boundary."""

    def test_uses_actor_user_id_when_calling_service(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-123")
        mock_projects = [MagicMock(), MagicMock()]
        mock_project_service.list_projects.return_value = mock_projects

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(list_projects(actor=actor, db=mock_db))

        mock_project_service.list_projects.assert_called_once_with(mock_db, "user-123")
        mock_success.assert_called_once_with(
            data=mock_projects, message="Projects retrieved successfully"
        )

    def test_different_actor_user_id_passed_to_service(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="different-user-456")
        mock_project_service.list_projects.return_value = []

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(list_projects(actor=actor, db=mock_db))

        mock_project_service.list_projects.assert_called_once_with(
            mock_db, "different-user-456"
        )


class TestGetProjectActorBoundary:
    """Tests for get_project endpoint Actor boundary."""

    def test_uses_actor_user_id_and_project_id(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-123")
        project_id = uuid.uuid4()
        mock_project = MagicMock()
        mock_project_service.get_project.return_value = mock_project

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(get_project(project_id=project_id, actor=actor, db=mock_db))

        mock_project_service.get_project.assert_called_once_with(
            mock_db, "user-123", project_id
        )
        mock_success.assert_called_once_with(
            data=mock_project, message="Project retrieved successfully"
        )

    def test_project_id_passed_unchanged(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-xyz")
        project_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_project = MagicMock()
        mock_project_service.get_project.return_value = mock_project

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(get_project(project_id=project_id, actor=actor, db=mock_db))

        call_args = mock_project_service.get_project.call_args
        assert call_args.args[2] == project_id


class TestCreateProjectActorBoundary:
    """Tests for create_project endpoint Actor boundary."""

    def test_uses_actor_user_id_and_request(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-123")
        mock_request = MagicMock()
        mock_request.name = "Test Project"
        mock_project = MagicMock()
        mock_project_service.create_project.return_value = mock_project

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(create_project(request=mock_request, actor=actor, db=mock_db))

        mock_project_service.create_project.assert_called_once_with(
            mock_db, "user-123", mock_request
        )
        mock_success.assert_called_once_with(
            data=mock_project, message="Project created successfully"
        )

    def test_request_object_passed_unchanged(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-xyz")
        mock_request = MagicMock()
        mock_request.name = "Another Project"
        mock_project = MagicMock()
        mock_project_service.create_project.return_value = mock_project

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(create_project(request=mock_request, actor=actor, db=mock_db))

        call_args = mock_project_service.create_project.call_args
        assert call_args.args[2] is mock_request


class TestUpdateProjectActorBoundary:
    """Tests for update_project endpoint Actor boundary."""

    def test_uses_actor_user_id_project_id_and_request(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-123")
        project_id = uuid.uuid4()
        mock_request = MagicMock()
        mock_project = MagicMock()
        mock_project_service.update_project.return_value = mock_project

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                update_project(
                    project_id=project_id, request=mock_request, actor=actor, db=mock_db
                )
            )

        mock_project_service.update_project.assert_called_once_with(
            mock_db, "user-123", project_id, mock_request
        )
        mock_success.assert_called_once_with(
            data=mock_project, message="Project updated successfully"
        )

    def test_project_id_and_request_passed_unchanged(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-xyz")
        project_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
        mock_request = MagicMock()
        mock_project = MagicMock()
        mock_project_service.update_project.return_value = mock_project

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                update_project(
                    project_id=project_id, request=mock_request, actor=actor, db=mock_db
                )
            )

        call_args = mock_project_service.update_project.call_args
        assert call_args.args[2] == project_id
        assert call_args.args[3] is mock_request


class TestDeleteProjectActorBoundary:
    """Tests for delete_project endpoint Actor boundary."""

    def test_uses_actor_user_id_and_project_id(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-123")
        project_id = uuid.uuid4()

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(delete_project(project_id=project_id, actor=actor, db=mock_db))

        mock_project_service.delete_project.assert_called_once_with(
            mock_db, "user-123", project_id
        )

    def test_returns_id_in_response_data(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-xyz")
        project_id = uuid.UUID("00000000-0000-0000-0000-000000000003")

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(delete_project(project_id=project_id, actor=actor, db=mock_db))

        mock_success.assert_called_once_with(
            data={"id": project_id}, message="Project deleted successfully"
        )

    def test_project_id_passed_unchanged(
        self,
        mock_db: MagicMock,
        mock_project_service: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        actor = Actor(user_id="user-abc")
        project_id = uuid.UUID("00000000-0000-0000-0000-000000000004")

        monkeypatch.setattr("app.api.v1.projects.service", mock_project_service)

        with patch("app.api.v1.projects.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(delete_project(project_id=project_id, actor=actor, db=mock_db))

        call_args = mock_project_service.delete_project.call_args
        assert call_args.args[2] == project_id
