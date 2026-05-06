from app.services.run_dispatch_claim import RunDispatchClaim


def test_run_dispatch_claim_run_id_annotation_is_object() -> None:
    """Regression: run_id should be typed as object, not Any."""
    import typing

    hints = typing.get_type_hints(RunDispatchClaim)
    assert hints["run_id"] is object


def test_run_dispatch_claim_parses_backend_payload() -> None:
    claim = RunDispatchClaim.from_payload(
        {
            "run": {
                "run_id": "run-1",
                "session_id": "sess-1",
                "permission_mode": "acceptEdits",
            },
            "user_id": "user-1",
            "prompt": "do work",
            "sdk_session_id": "sdk-1",
            "config_snapshot": {
                "container_mode": "persistent",
                "container_id": "container-1",
            },
        }
    )

    assert claim is not None
    assert claim.run_id == "run-1"
    assert claim.session_id == "sess-1"
    assert claim.user_id == "user-1"
    assert claim.prompt == "do work"
    assert claim.sdk_session_id == "sdk-1"
    assert claim.permission_mode == "acceptEdits"
    assert claim.config_snapshot == {
        "container_mode": "persistent",
        "container_id": "container-1",
    }
    assert claim.container_mode == "persistent"
    assert claim.container_id == "container-1"


def test_run_dispatch_claim_ignores_sdk_session_for_scheduled_runs() -> None:
    claim = RunDispatchClaim.from_payload(
        {
            "run": {
                "run_id": "run-1",
                "session_id": "sess-1",
                "scheduled_task_id": "scheduled-1",
            },
            "user_id": "user-1",
            "prompt": "do work",
            "sdk_session_id": "sdk-1",
        }
    )

    assert claim is not None
    assert claim.sdk_session_id is None
    assert claim.permission_mode == "default"
    assert claim.config_snapshot == {}
    assert claim.container_mode == "ephemeral"
    assert claim.container_id is None


def test_run_dispatch_claim_rejects_missing_required_fields() -> None:
    assert (
        RunDispatchClaim.from_payload(
            {
                "run": {"run_id": "run-1", "session_id": "sess-1"},
                "user_id": "user-1",
                "prompt": "",
            }
        )
        is None
    )


def test_run_dispatch_claim_preserves_raw_run_id_for_backend_state_calls() -> None:
    claim = RunDispatchClaim.from_payload(
        {
            "run": {"run_id": 1, "session_id": "sess-1"},
            "user_id": "user-1",
            "prompt": "do work",
        }
    )

    assert claim is not None
    assert claim.run_id == 1
    assert claim.run_id_str == "1"


def test_run_dispatch_claim_defaults_invalid_config_snapshot() -> None:
    claim = RunDispatchClaim.from_payload(
        {
            "run": {"run_id": "run-1", "session_id": "sess-1"},
            "user_id": "user-1",
            "prompt": "do work",
            "config_snapshot": ["not", "a", "dict"],
        }
    )

    assert claim is not None
    assert claim.config_snapshot == {}
