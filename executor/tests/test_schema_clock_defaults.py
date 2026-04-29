from app.core.clock import utc_now
from app.schemas.callback import AgentCallbackRequest
from app.schemas.state import WorkspaceState


def test_datetime_schema_defaults_use_shared_clock_factory() -> None:
    assert AgentCallbackRequest.model_fields["time"].default_factory is utc_now
    assert WorkspaceState.model_fields["last_change"].default_factory is utc_now
