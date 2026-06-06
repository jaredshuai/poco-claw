import typing
from typing import get_args, get_origin

from app.schemas.run import RunClaimResponse, RunResponse


def _assert_optional_dict_str_object(annotation: object) -> None:
    assert annotation is not None
    assert annotation is not dict
    assert "Any" not in str(annotation)
    args = get_args(annotation)
    assert type(None) in args
    dict_annotation = next((arg for arg in args if get_origin(arg) is dict), None)
    assert dict_annotation is not None
    assert get_args(dict_annotation) == (str, object)


def _assert_optional_list_dict_str_object(annotation: object) -> None:
    assert annotation is not None
    assert "Any" not in str(annotation)
    args = get_args(annotation)
    assert type(None) in args
    list_annotation = next((arg for arg in args if get_origin(arg) is list), None)
    assert list_annotation is not None
    (item_annotation,) = get_args(list_annotation)
    assert get_origin(item_annotation) is dict
    assert get_args(item_annotation) == (str, object)


def test_run_response_payload_annotations_are_typed_json_objects() -> None:
    """Regression: run response payload fields avoid bare dict annotations."""
    hints = typing.get_type_hints(RunResponse)

    for field_name in (
        "config_snapshot",
        "config_layers",
        "permission_policy_snapshot",
    ):
        _assert_optional_dict_str_object(hints[field_name])

    _assert_optional_list_dict_str_object(hints["resolved_hook_specs"])


def test_run_claim_response_config_snapshot_annotation_is_typed_json_object() -> None:
    """Regression: claim response config snapshot avoids bare dict annotations."""
    hints = typing.get_type_hints(RunClaimResponse)

    _assert_optional_dict_str_object(hints["config_snapshot"])


def test_run_response_normalizer_annotations_are_typed_json_objects() -> None:
    """Regression: run response normalizers return typed JSON object payloads."""
    dict_hints = typing.get_type_hints(RunResponse._normalize_optional_dict)
    list_hints = typing.get_type_hints(RunResponse._normalize_optional_list)

    _assert_optional_dict_str_object(dict_hints["return"])
    _assert_optional_list_dict_str_object(list_hints["return"])
