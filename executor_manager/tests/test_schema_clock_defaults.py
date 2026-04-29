from app.schemas.callback import AgentCallbackRequest
from app.services.clock import utc_now


def test_callback_request_default_time_uses_shared_clock_factory() -> None:
    assert AgentCallbackRequest.model_fields["time"].default_factory is utc_now
