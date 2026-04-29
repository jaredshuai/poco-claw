from unittest.mock import MagicMock

import pytest

from app.repositories.scheduled_task_repository import ScheduledTaskRepository


def test_claim_due_for_update_requires_explicit_now():
    with pytest.raises(TypeError):
        ScheduledTaskRepository.claim_due_for_update(MagicMock())
