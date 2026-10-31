"""공통 선택지와 학사 소속의 공개 응답 DTO를 정의한다."""

from typing import Annotated

from pydantic import AfterValidator, Field, HttpUrl, StrictStr

from app.core.http.schemas import PositiveBigInt, RequestDTO, ResponseDTO
from app.rules.text import normalize_text


class CatalogItem(ResponseDTO):
    """화면 표시와 신규 선택 가능 여부를 제공하는 공통 선택지."""

    code: Annotated[
        str,
        Field(
            min_length=1,
            max_length=64,
            description="선택지를 식별하는 목록 내 불변 코드.",
        ),
    ]
    display_name: str = Field(description="선택지의 화면 표시명.")
    is_selectable: bool = Field(
        description=(
            "현재 새로 선택할 수 있는 항목인지 여부. 비활성 항목도 "
            "기존 값 표시용으로 제공됩니다."
        )
    )
    sort_order: Annotated[
        int,
        Field(
            ge=-2147483648,
            le=2147483647,
            description=(
                "목록 정렬값. 오름차순으로 정렬하며 같은 값이면 코드 순으로 정렬합니다."
            ),
        ),
    ]


class AvatarPreset(CatalogItem):
    """프로필 이미지 선택지와 제공 이미지의 주소."""

    asset_url: HttpUrl = Field(description="선택한 프로필 이미지의 HTTP(S) 주소.")


class Catalogs(ResponseDTO):
    """프로필과 공고·팀에서 함께 사용하는 공통 선택지 목록."""

    fields: list[CatalogItem] = Field(description="관심 분야와 공모전 분야 선택지.")
    roles: list[CatalogItem] = Field(description="희망 역할과 팀 모집 역할 선택지.")
    skills: list[CatalogItem] = Field(description="보유 역량 선택지.")
    academic_statuses: list[CatalogItem] = Field(description="학적 상태 선택지.")
    grades: list[CatalogItem] = Field(description="학년 선택지.")
    weekly_availability_ranges: list[CatalogItem] = Field(
        description="주당 참여 가능 시간 구간 선택지."
    )
    avatar_presets: list[AvatarPreset] = Field(
        description="프로필 이미지 선택지와 이미지 주소."
    )


class AcademicUnitResponse(ResponseDTO):
    """부모 연결로 학사 소속 계층을 구성하는 항목."""

    id: PositiveBigInt = Field(
        description=("DB가 발급한 학사 항목 ID를 나타내는 양의 십진 문자열.")
    )
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100,
            description="학사 항목의 표시명. 항목 식별에는 id를 사용합니다.",
        ),
    ]
    parent_id: PositiveBigInt | None = Field(
        description=("부모 학사 항목 ID의 십진 문자열. 루트 단과대학이면 null입니다.")
    )
    is_selectable: bool = Field(
        description=(
            "해당 학사 항목의 신규 선택 가능 여부. 선택 시 상위 "
            "항목의 활성 상태도 확인합니다."
        )
    )


CourseCode = Annotated[
    StrictStr, AfterValidator(normalize_text), Field(min_length=1, max_length=64)
]


class CourseSummary(ResponseDTO):
    """프로필·추천에서 사용하는 과목의 학수번호와 대표 이름."""

    code: str
    name: str


class CourseCatalogItem(CourseSummary):
    """과목 검색에서 대표 이름과 과거 이름·개설학과를 구분한다."""

    aliases: list[str]
    departments: list[str]


class CoursesQuery(RequestDTO):
    """과목 코드·이름·별칭 검색과 페이지 조건."""

    q: (
        Annotated[StrictStr, AfterValidator(normalize_text), Field(max_length=100)]
        | None
    ) = None
    page: Annotated[int, Field(ge=1, le=9007199254740991)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20
