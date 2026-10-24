"""사람 검색어의 잘못된 Unicode를 거부하고 정상 Unicode를 보존한다."""

import pytest
from pydantic import ValidationError

from app.schemas.profiles import PeopleQuery


@pytest.mark.parametrize("query", ["\x00", "검색\x00어", "\ud800", "\udfff"])
def test_people_query_rejects_invalid_database_text(query: str) -> None:
    with pytest.raises(ValidationError) as error:
        PeopleQuery(q=query)
    assert error.value.errors()[0]["loc"] == ("q",)


def test_people_query_preserves_valid_text() -> None:
    query = "  e\u0301 한글 👩‍💻 %_\n"
    assert PeopleQuery(q=query).q == query
