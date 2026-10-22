import pytest
from pydantic import ValidationError

from app.core.http.schemas import Page, PageMeta, RequestDTO, ResponseDTO, Success


class ChildRequest(RequestDTO):
    display_name: str
    optional_note: str | None = None


class ExampleRequest(RequestDTO):
    display_name: str
    nullable_note: str | None
    children: list[ChildRequest]
    metadata: dict[str, str]


class ExampleResponse(ResponseDTO):
    display_name: str
    nullable_note: str | None


def valid_request() -> dict[str, object]:
    return {
        "displayName": "sample",
        "nullableNote": None,
        "children": [{"displayName": "child"}],
        "metadata": {"user_defined_key": "keep_this_value"},
    }


def test_request_aliases_do_not_transform_map_keys_or_values() -> None:
    request = ExampleRequest.model_validate(valid_request())

    assert request.display_name == "sample"
    assert request.children[0].optional_note is None
    assert request.metadata == {"user_defined_key": "keep_this_value"}


@pytest.mark.parametrize(
    "changes",
    [
        {"display_name": "extra"},
        {"optional_typo": "extra"},
        {"children": [{"display_name": "child"}]},
        {"children": [{"displayName": "child", "optional_note": "extra"}]},
    ],
)
def test_request_rejects_unknown_and_snake_case_fields(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ExampleRequest.model_validate(valid_request() | changes)


def test_required_nullable_field_cannot_be_omitted() -> None:
    data = valid_request()
    del data["nullableNote"]

    with pytest.raises(ValidationError):
        ExampleRequest.model_validate(data)


def test_response_uses_python_names_and_serializes_explicit_null() -> None:
    result = Success[ExampleResponse](
        data=ExampleResponse(display_name="sample", nullable_note=None)
    )

    assert result.model_dump(mode="json") == {
        "data": {"displayName": "sample", "nullableNote": None}
    }


def test_response_rejects_undeclared_sensitive_fields() -> None:
    with pytest.raises(ValidationError):
        ExampleResponse.model_validate(
            {"displayName": "sample", "nullableNote": None, "password": "secret"}
        )


@pytest.mark.parametrize("values", [{"data": None}, {}])
def test_success_requires_the_declared_nonnullable_data(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Success[ExampleResponse].model_validate(values)

    schema = Success[ExampleResponse].model_json_schema()
    assert schema["required"] == ["data"]
    assert schema["properties"]["data"] == {"$ref": "#/$defs/ExampleResponse"}


def test_page_has_one_envelope_and_explicit_empty_metadata() -> None:
    page = Page[ExampleResponse](
        data=[], pagination=PageMeta(page=1, page_size=20, total=0, total_pages=0)
    )

    assert page.model_dump(mode="json") == {
        "data": [],
        "pagination": {"page": 1, "pageSize": 20, "total": 0, "totalPages": 0},
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"page": 0},
        {"pageSize": 101},
        {"total": -1},
        {"totalPages": 0.5},
        {"page": True},
        {"total": 9007199254740992},
    ],
)
def test_page_rejects_invalid_wire_counts(changes: dict[str, object]) -> None:
    values = {"page": 1, "pageSize": 20, "total": 0, "totalPages": 0}
    with pytest.raises(ValidationError):
        PageMeta.model_validate(values | changes)
