"""실존 인물을 참조하지 않는 가상 콘텐츠와 이전 시드의 고정 비교 기준."""

import random

from app.rules.catalogs import (
    FieldCode,
    GradeCode,
    ProfileImageCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
)
from app.schemas.profile_write import ProfileWrite

# 기존 개발 DB의 사용자 편집 보호를 위한 구버전 콘텐츠다. 새 문구와 함께 고치지 않는다.
FAMILY_NAMES = tuple(
    "김 이 박 최 정 강 조 윤 장 임 한 오 서 신 권 황 안 송 전 홍".split()
)
GIVEN_NAMES = tuple(
    "민준 서연 지호 하은 도윤 수아 예준 지우 시우 서윤 유진 하준 은서 준서 채원".split()
)
ROLE_SKILLS = (
    ("service_planning", "document_writing", "market_research"),
    ("ui_ux", "graphic_design", "presentation_design"),
    ("programming", "data_analysis", "data_visualization"),
    ("social_media_marketing", "content_planning", "video_editing"),
    ("market_research", "data_analysis", "document_writing"),
    ("public_speaking", "presentation_design", "content_planning"),
)
TOPICS = (
    "캠퍼스 생활을 편리하게 만드는 서비스",
    "지역 상권을 연결하는 플랫폼",
    "일상 속 탄소 절감 프로젝트",
    "누구나 쉽게 배우는 교육 콘텐츠",
    "접근성을 고려한 모바일 경험",
    "데이터로 찾는 지역 문제 해결책",
    "청년의 건강한 생활 습관",
    "문화와 기술을 연결하는 전시",
    "작은 브랜드를 위한 콘텐츠",
    "지역 사회에 도움이 되는 공공 서비스",
)


def legacy_profile_input(index: int, academic_id: int) -> ProfileWrite:
    """실제 사람의 정보를 사용하지 않고 enum과 입력 DTO에 맞는 프로필을 만든다."""
    rng = random.Random(20261026 + index)
    role = list(RoleCode)[index % len(RoleCode)]
    fields = rng.sample(list(FieldCode), 1 + index % 3)
    roles = [role]
    if index % 2:
        roles.append(list(RoleCode)[(index + 1) % len(RoleCode)])
    skills = list(ROLE_SKILLS[index % len(RoleCode)])
    if index % 4 == 0:
        skills = []
    elif index % 3 == 0:
        skills = list(dict.fromkeys([*skills, rng.choice(list(SkillCode)).value]))
    state = (
        "unspecified" if index % 10 == 9 else "none" if index % 3 == 0 else "provided"
    )
    status = (
        "graduated"
        if index % 12 == 10
        else "on_leave"
        if index % 12 == 11
        else "enrolled"
    )
    sparse = index % 10 == 9
    name = (
        FAMILY_NAMES[index // len(GIVEN_NAMES)] + GIVEN_NAMES[index % len(GIVEN_NAMES)]
    )
    return ProfileWrite.model_validate(
        {
            "expectedVersion": "0",
            "realName": name,
            "profileImageCode": None
            if sparse
            else list(ProfileImageCode)[(index // 5) % 5].value,
            "academicStatusCode": None if sparse else status,
            "gradeCode": None
            if sparse
            else "not_applicable"
            if status == "graduated"
            else list(GradeCode)[index % 4].value,
            "weeklyAvailabilityCode": None
            if sparse
            else list(WeeklyAvailabilityCode)[index % 4].value,
            "academicUnitId": None if sparse else str(academic_id),
            "experienceState": state,
            "experienceBody": (
                f"{TOPICS[index % 10]}를 주제로 팀 프로젝트에 참여했습니다. "
                f"{role.display_name} 역할로 문제 정의부터 결과 발표까지 "
                "진행하고 회고를 정리했습니다."
            )
            if state == "provided"
            else None,
            "introduction": None
            if sparse
            else (
                f"{fields[0].display_name}에 관심이 있는 {name}입니다. "
                f"{role.display_name} 역할로 {TOPICS[index % 10]}를 "
                "함께 만들고 싶습니다. "
                + (
                    "주말 온라인 회의가 편합니다."
                    if index % 2
                    else "평일 저녁에 꾸준히 참여할 수 있습니다."
                )
            ),
            "fieldCodes": [c.value for c in fields],
            "roleCodes": [c.value for c in roles],
            "skillCodes": skills,
            "portfolio": None
            if sparse or index % 3 == 0
            else {
                "url": f"https://example.com/portfolio/devuser{index + 1:03d}",
                "title": f"{name}의 개발용 예시 포트폴리오",
            },
        }
    )


PROJECTS = (
    "빈 강의실을 찾는 캠퍼스 지도",
    "동네 가게를 소개하는 산책 안내서",
    "다회용 컵 반납을 돕는 캠페인",
    "처음 배우는 사람을 위한 공부 노트",
    "읽기 편한 교내 행사 안내 화면",
    "버스 정류장 이용 현황 시각화",
    "짧은 산책을 기록하는 생활 일지",
    "학생 작품을 모아 보는 온라인 전시",
    "동아리 소식을 전하는 짧은 영상",
    "도서관 이용을 돕는 안내 서비스",
)
ROLE_WORK = (
    "사용자 의견을 모아 필요한 기능을 정리했습니다.",
    "화면 흐름을 그려 보고 읽기 편한 시안을 만들었습니다.",
    "작은 기능부터 구현하고 동작을 확인하는 테스트를 작성했습니다.",
    "소개 문구와 게시 계획을 만들고 반응을 정리했습니다.",
    "공개 자료를 비교하고 출처가 있는 조사 노트를 만들었습니다.",
    "팀의 생각을 발표 자료로 엮고 전달 순서를 다듬었습니다.",
)
COLLABORATION = (
    "아이디어를 작게 나누어 하나씩 완성하는 편입니다.",
    "서로의 초안을 보며 구체적으로 의견을 나누고 싶습니다.",
    "진행 상황을 문서로 남기며 차근차근 협업하고 싶습니다.",
    "처음 맡는 일도 질문하고 연습하며 함께 배워 가겠습니다.",
    "역할을 정한 뒤 짧게 점검하며 일정에 맞춰 움직이고 싶습니다.",
)
TEAM_NAMES = (
    "모아봄",
    "작은물결",
    "한걸음",
    "이어봄",
    "새길",
    "다음장",
    "초록점",
    "오롯이",
    "생각마루",
    "나란히",
)


def profile_input(index: int, academic_id: int) -> ProfileWrite:
    """카탈로그·선택 상태는 유지하고 가상 이름과 프로젝트 문장만 바꾼다."""
    old = legacy_profile_input(index, academic_id)
    data = old.model_dump(mode="json", by_alias=True)
    project = PROJECTS[index % len(PROJECTS)]
    data["realName"] = f"{old.real_name} [테스트 P{index + 1:03d}]"
    if old.experience_state == "provided":
        data["experienceBody"] = (
            f'가상 교내 프로젝트 "{project}"에 참여했습니다. '
            + ROLE_WORK[index % len(ROLE_WORK)]
        )
    if old.introduction is not None:
        data["introduction"] = (
            f'{old.real_name}입니다. "{project}" 같은 주제에 관심이 있습니다. '
            + COLLABORATION[(index // len(PROJECTS)) % len(COLLABORATION)]
        )
    if old.portfolio is not None:
        data["portfolio"] = {
            "url": str(old.portfolio.url),
            "title": f"{old.real_name}의 가상 프로젝트 기록",
        }
    return ProfileWrite.model_validate(data)


def legacy_team_content(index: int, contest_title: str) -> tuple[str, str]:
    names = (
        "드림메이커",
        "캠퍼스랩",
        "넥스트스텝",
        "아이디어온",
        "함께도전",
        "그린웨이",
    )
    return (
        f"{names[index % 6]} {index + 1:02d}",
        f"[개발용 가상팀] {contest_title}에 함께 도전할 팀원을 찾습니다. "
        f"{TOPICS[index % 10]}에 관심이 있습니다. "
        "매주 진행 상황을 공유하고 역할별 결과물을 함께 검토합니다.",
    )


def team_content(index: int, contest_title: str) -> tuple[str, str]:
    # 공고 원문은 그대로 두고 소개에 인용할 제목만 짧게 표현한다.
    title = contest_title if len(contest_title) <= 120 else contest_title[:117] + "..."
    return (
        f"{TEAM_NAMES[index % len(TEAM_NAMES)]} [테스트 T{index + 1:03d}]",
        f'"{title}"에 도전하는 가상 프로젝트 팀입니다. '
        f'"{PROJECTS[index % len(PROJECTS)]}"에서 아이디어를 출발해 보려 합니다. '
        + COLLABORATION[(index // len(PROJECTS)) % len(COLLABORATION)]
        + " 함께 기획을 정리하고 작은 결과물부터 만들어 갈 팀원을 찾습니다.",
    )
