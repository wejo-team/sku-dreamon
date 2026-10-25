"""프로필 전체 저장과 버전 기반 공개 전환의 요청 계약을 정의한다."""

from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    Field,
    StrictBool,
    StrictStr,
    model_validator,
)

from app.core.http.schemas import NonnegativeBigInt, PositiveBigInt, RequestDTO, Version
from app.rules.text import normalize_text

NormalizedText = Annotated[StrictStr, AfterValidator(normalize_text)]
Name = Annotated[NormalizedText, Field(min_length=1, max_length=50)]
OptionalTitle = Annotated[NormalizedText, Field(max_length=50)]
Introduction = Annotated[NormalizedText, Field(max_length=300)]
ExperienceBody = Annotated[NormalizedText, Field(max_length=500)]


class PortfolioWrite(RequestDTO):
    """HTTP(S) 링크 한 개와 선택 제목. 제거는 상위 필드의 null로 표현한다."""

    url: AnyHttpUrl = Field(description="포트폴리오 HTTP(S) 절대 URL.")
    title: OptionalTitle | None = Field(description="선택 제목. 최대 50 코드 포인트.")


class ProfileWrite(RequestDTO):
    """전체 편집값을 저장한다. 공개 여부와 계정 식별자는 입력받지 않는다."""

    expected_version: NonnegativeBigInt = Field(
        description="최초 저장 0, 수정은 조회 버전."
    )
    real_name: Name = Field(description="실명. NFC·trim 후 1~50 코드 포인트.")
    profile_image_code: StrictStr | None = Field(description="프로필 이미지 코드.")
    academic_status_code: StrictStr | None = Field(description="학적 코드.")
    grade_code: StrictStr | None = Field(description="학년 코드.")
    weekly_availability_code: StrictStr | None = Field(
        description="주당 참여 시간 코드."
    )
    academic_unit_id: PositiveBigInt | None = Field(description="학사 항목 ID.")
    experience_state: Literal["unspecified", "none", "provided"] = Field(
        description="경험 상태."
    )
    experience_body: ExperienceBody | None = Field(
        description="경험 본문. 최대 500 코드 포인트."
    )
    introduction: Introduction | None = Field(
        description="자기소개. 최대 300 코드 포인트."
    )
    field_codes: list[StrictStr] = Field(
        min_length=1, max_length=3, description="관심 분야 1~3개."
    )
    role_codes: list[StrictStr] = Field(
        min_length=1, max_length=2, description="희망 역할 1~2개."
    )
    skill_codes: list[StrictStr] = Field(description="보유 역량. 중복 불가.")
    portfolio: PortfolioWrite | None = Field(description="포트폴리오 또는 null.")

    @model_validator(mode="after")
    def normalize_values(self) -> Self:
        for values in (self.field_codes, self.role_codes, self.skill_codes):
            if len(values) != len(set(values)):
                raise ValueError("Selections must be distinct")
        if self.experience_state != "provided":
            self.experience_body = None
        elif not self.experience_body:
            self.experience_state, self.experience_body = "unspecified", None
        self.introduction = self.introduction or None
        if self.portfolio is not None:
            self.portfolio.title = self.portfolio.title or None
        return self


class VisibilityWrite(RequestDTO):
    """현재 버전에 대한 전체 프로필 공개 전환 요청."""

    expected_version: Version = Field(description="현재 프로필 버전.")
    is_public: StrictBool = Field(description="요청하는 전체 프로필 공개 여부.")
