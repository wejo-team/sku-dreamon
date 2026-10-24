"""표시명과 분리한 불변 선택 코드와 같은 원본의 표시 정보를 정의한다."""

from enum import StrEnum
from typing import Self

from app.core.exceptions import AppError


class CatalogCode(StrEnum):
    display_name: str
    sort_order: int
    is_selectable: bool

    def __new__(
        cls,
        code: str,
        display_name: str = "",
        sort_order: int = 0,
        is_selectable: bool = True,
    ) -> Self:
        member = str.__new__(cls, code)
        member._value_ = code
        member.display_name = display_name
        member.sort_order = sort_order
        member.is_selectable = is_selectable
        return member


class FieldCode(CatalogCode):
    IT_TECHNOLOGY = "it_technology", "IT·기술", 0
    BUSINESS_STARTUP = "business_startup", "경영·창업", 1
    DESIGN = "design", "디자인", 2
    SOCIETY_CULTURE = "society_culture", "사회·문화", 3
    ENVIRONMENT = "environment", "환경", 4
    EDUCATION = "education", "교육", 5
    MEDIA_CONTENT = "media_content", "미디어·콘텐츠", 6
    HEALTH_MEDICAL = "health_medical", "보건·의료", 7
    POLICY = "policy", "정책", 8
    PUBLIC = "public", "공공", 9


class RoleCode(CatalogCode):
    PLANNING = "planning", "기획", 0
    DESIGN = "design", "디자인", 1
    DEVELOPMENT = "development", "개발", 2
    MARKETING = "marketing", "마케팅", 3
    RESEARCH = "research", "자료조사", 4
    PRESENTATION = "presentation", "발표", 5


class SkillCode(CatalogCode):
    PROGRAMMING = "programming", "프로그래밍", 0
    UI_UX = "ui_ux", "UI/UX", 1
    DATA_ANALYSIS = "data_analysis", "데이터분석", 2
    VIDEO_EDITING = "video_editing", "영상 편집", 3
    DOCUMENT_WRITING = "document_writing", "문서 작성", 4
    SERVICE_PLANNING = "service_planning", "서비스 기획", 5
    MARKET_RESEARCH = "market_research", "시장 조사", 6
    GRAPHIC_DESIGN = "graphic_design", "그래픽 디자인", 7
    PRESENTATION_DESIGN = "presentation_design", "PPT 제작", 8
    DATA_VISUALIZATION = "data_visualization", "데이터 시각화", 9
    SOCIAL_MEDIA_MARKETING = "social_media_marketing", "SNS 마케팅", 10
    CONTENT_PLANNING = "content_planning", "콘텐츠 기획", 11
    PUBLIC_SPEAKING = "public_speaking", "발표·스피치", 12


class AcademicStatusCode(CatalogCode):
    ENROLLED = "enrolled", "재학", 0
    ON_LEAVE = "on_leave", "휴학", 1
    GRADUATED = "graduated", "졸업", 2


class GradeCode(CatalogCode):
    YEAR_1 = "year_1", "1학년", 0
    YEAR_2 = "year_2", "2학년", 1
    YEAR_3 = "year_3", "3학년", 2
    YEAR_4_OR_HIGHER = "year_4_or_higher", "4학년 이상", 3
    NOT_APPLICABLE = "not_applicable", "해당 없음", 4


class WeeklyAvailabilityCode(CatalogCode):
    UNDER_5 = "under_5", "5시간 미만", 0
    FROM_5_TO_10 = "from_5_to_10", "5~10시간 미만", 1
    FROM_10_TO_20 = "from_10_to_20", "10~20시간 미만", 2
    AT_LEAST_20 = "at_least_20", "20시간 이상", 3


class ProfileImageCode(CatalogCode):
    SKON = "skon", "스콘", 0
    ARTI = "arti", "아티", 1
    DMO = "dmo", "디모", 2
    BART = "bart", "비아트", 3
    CONVER = "conver", "컨버", 4

    @property
    def asset_url(self) -> str:
        filename = {"dmo": "d-mo", "bart": "b-art"}.get(self.value, self.value)
        return (
            "https://www.skuniv.ac.kr/wp-content/themes/_tw/theme/assets/images/"
            f"mascot/{filename}-head.png"
        )


def validate_catalog_selection[Code: CatalogCode](
    enum_type: type[Code], code: str | None, previous_code: str | None = None
) -> Code | None:
    """종류별 신규 선택을 검증하되 저장된 비활성 코드의 유지는 허용한다."""
    if code is None:
        return None
    try:
        value = enum_type(code)
    except ValueError as error:
        raise AppError(
            409, "INVALID_CATALOG_SELECTION", "선택지를 다시 확인해 주세요."
        ) from error
    if not value.is_selectable and code != previous_code:
        raise AppError(409, "INVALID_CATALOG_SELECTION", "선택지를 다시 확인해 주세요.")
    return value
