"""검색어의 PostgreSQL UTF-8 표현 가능성만 검사하고 정상 입력은 보존한다."""

import pytest
from pydantic import ValidationError

from app.domains.profiles.schemas import PeopleQuery
from app.domains.teams.schemas import AllTeamSearch, TeamSearch


@pytest.mark.parametrize("schema", [TeamSearch, AllTeamSearch, PeopleQuery])
@pytest.mark.parametrize("query", ["\x00", "검색\x00어", "\ud800", "\udfff"])
def test_search_rejects_text_postgresql_cannot_represent(
    schema: type[TeamSearch] | type[PeopleQuery], query: str
) -> None:
    with pytest.raises(ValidationError) as error:
        schema(q=query)
    assert error.value.errors()[0]["loc"] == ("q",)


@pytest.mark.parametrize("schema", [TeamSearch, AllTeamSearch, PeopleQuery])
@pytest.mark.parametrize(
    "query", [None, "", "  개발  ", "e\u0301 한글 👩‍💻 %_", "줄\n바꿈"]
)
def test_search_preserves_representable_text_without_new_normalization(
    schema: type[TeamSearch] | type[PeopleQuery], query: str | None
) -> None:
    assert schema(q=query).q == query
