"""Tests for memories API actor boundary."""

import asyncio
import uuid
from unittest.mock import MagicMock, patch

from app.api.v1 import memories
from app.core.identity import Actor
from app.schemas.memory import (
    MemoryCreateJobEnqueueResponse,
    MemoryCreateJobResponse,
    MemoryCreateRequest,
    MemoryMessage,
    MemorySearchRequest,
)


def test_create_memories_uses_actor_user_id_and_passes_request():
    """create_memories should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="creator-user-123", auth_source="test")
    mock_db = MagicMock()
    request = MemoryCreateRequest(
        messages=[MemoryMessage(role="user", content="test")],
        run_id="run-456",
    )
    mock_result = MemoryCreateJobEnqueueResponse(
        job_id=uuid.uuid4(),
        status="pending",
    )

    with (
        patch.object(
            memories.memory_create_job_service,
            "enqueue_create",
            return_value=mock_result,
        ) as mock_enqueue,
        patch.object(memories.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()
        background_tasks = MagicMock()

        result = asyncio.run(
            memories.create_memories(
                request=request,
                background_tasks=background_tasks,
                actor=actor,
                db=mock_db,
            )
        )

        mock_enqueue.assert_called_once()
        call_args = mock_enqueue.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "creator-user-123"
        assert call_args[1]["request"] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Memory create job queued successfully"
        )
        assert result is not None


def test_create_memories_preserves_background_task_scheduling():
    """create_memories should schedule background task with job_id."""
    actor = Actor(user_id="bg-user-789", auth_source="trusted_user_header")
    mock_db = MagicMock()
    request = MemoryCreateRequest(messages=[MemoryMessage(role="user", content="x")])
    job_id = uuid.uuid4()
    mock_result = MemoryCreateJobEnqueueResponse(job_id=job_id, status="pending")

    with (
        patch.object(
            memories.memory_create_job_service,
            "enqueue_create",
            return_value=mock_result,
        ),
        patch.object(memories.Response, "success"),
    ):
        background_tasks = MagicMock()

        asyncio.run(
            memories.create_memories(
                request=request,
                background_tasks=background_tasks,
                actor=actor,
                db=mock_db,
            )
        )

        background_tasks.add_task.assert_called_once_with(
            memories.memory_create_job_service.process_create_job,
            job_id,
        )


def test_get_active_memory_create_job_uses_actor_user_id():
    """get_active_memory_create_job should use actor.user_id when calling the service."""
    actor = Actor(user_id="active-user-111", auth_source="test")
    mock_db = MagicMock()
    mock_result = MemoryCreateJobResponse(
        job_id=uuid.uuid4(),
        status="running",
    )

    with (
        patch.object(
            memories.memory_create_job_service,
            "get_active_job",
            return_value=mock_result,
        ) as mock_get,
        patch.object(memories.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            memories.get_active_memory_create_job(actor=actor, db=mock_db)
        )

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "active-user-111"
        mock_success.assert_called_once_with(
            data=mock_result, message="Active memory create job retrieved successfully"
        )
        assert result is not None


def test_get_memory_create_job_uses_actor_user_id_preserves_job_id():
    """get_memory_create_job should use actor.user_id and preserve job_id."""
    actor = Actor(user_id="job-user-222", auth_source="internal_token")
    mock_db = MagicMock()
    job_id = uuid.uuid4()
    mock_result = MemoryCreateJobResponse(
        job_id=job_id,
        status="completed",
    )

    with (
        patch.object(
            memories.memory_create_job_service,
            "get_job",
            return_value=mock_result,
        ) as mock_get,
        patch.object(memories.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            memories.get_memory_create_job(job_id=job_id, actor=actor, db=mock_db)
        )

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "job-user-222"
        assert call_args[1]["job_id"] == job_id
        mock_success.assert_called_once_with(
            data=mock_result, message="Memory create job retrieved successfully"
        )
        assert result is not None


def test_list_memories_uses_actor_user_id():
    """list_memories should use actor.user_id when calling the service."""
    actor = Actor(user_id="list-user-333", auth_source="test")
    mock_result = [{"id": "mem-1", "text": "test memory"}]

    with (
        patch.object(
            memories.memory_service,
            "list_memories",
            return_value=mock_result,
        ) as mock_list,
        patch.object(memories.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(memories.list_memories(actor=actor))

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[1]["user_id"] == "list-user-333"
        assert call_args[1]["run_id"] is None
        mock_success.assert_called_once_with(
            data=mock_result, message="Memories retrieved successfully"
        )
        assert result is not None


def test_list_memories_preserves_run_id():
    """list_memories should pass run_id through unchanged."""
    actor = Actor(user_id="run-user-444", auth_source="trusted_user_header")
    run_id = "run-abc-123"
    mock_result = []

    with (
        patch.object(
            memories.memory_service,
            "list_memories",
            return_value=mock_result,
        ) as mock_list,
        patch.object(memories.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(memories.list_memories(run_id=run_id, actor=actor))

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[1]["run_id"] == run_id
        assert result is not None


def test_search_memories_uses_actor_user_id_and_passes_request():
    """search_memories should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="search-user-555", auth_source="test")
    request = MemorySearchRequest(query="test query", run_id="run-xyz")
    mock_result = [{"id": "mem-2", "text": "matched memory"}]

    with (
        patch.object(
            memories.memory_service,
            "search_memories",
            return_value=mock_result,
        ) as mock_search,
        patch.object(memories.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(memories.search_memories(request=request, actor=actor))

        mock_search.assert_called_once()
        call_args = mock_search.call_args
        assert call_args[1]["user_id"] == "search-user-555"
        assert call_args[1]["request"] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Memories searched successfully"
        )
        assert result is not None


def test_delete_all_memories_uses_actor_user_id():
    """delete_all_memories should use actor.user_id when calling the service."""
    actor = Actor(user_id="delete-user-666", auth_source="internal_token")

    with (
        patch.object(
            memories.memory_service,
            "delete_all_memories",
            return_value=None,
        ) as mock_delete,
        patch.object(memories.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(memories.delete_all_memories(actor=actor))

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[1]["user_id"] == "delete-user-666"
        assert call_args[1]["run_id"] is None
        mock_success.assert_called_once_with(
            data={"deleted": True},
            message="All relevant memories deleted successfully",
        )
        assert result is not None


def test_delete_all_memories_preserves_run_id():
    """delete_all_memories should pass run_id through unchanged."""
    actor = Actor(user_id="run-delete-user-777", auth_source="test")
    run_id = "run-delete-999"

    with (
        patch.object(
            memories.memory_service,
            "delete_all_memories",
            return_value=None,
        ) as mock_delete,
        patch.object(memories.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(memories.delete_all_memories(run_id=run_id, actor=actor))

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[1]["run_id"] == run_id
        assert result is not None
