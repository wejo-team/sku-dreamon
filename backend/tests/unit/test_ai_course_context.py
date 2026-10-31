"""모델에 수강 과목의 코드·이름만 보내고 기존 개인정보 경계를 보존한다."""

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.catalogs import CourseSummary
from app.schemas.profiles import ProfileResponse
from app.services.ai_sources import profile_facts


def test_course_context_preserves_names_without_extra_profile_fields() -> None:
    profile = ProfileResponse(
        account_id=uuid4(),
        real_name="과목 등록 사용자",
        is_demo=False,
        profile_image_code=None,
        introduction=None,
        field_codes=["it_technology"],
        role_codes=["planning"],
        skill_codes=[],
        version="1",
        is_public=False,
        updated_at=datetime.now(UTC),
        academic_status_code=None,
        grade_code=None,
        weekly_availability_code=None,
        academic_unit_id="1",
        experience_state="unspecified",
        experience_body=None,
        portfolio=None,
        courses=[CourseSummary(code="GE1394", name="AI리터러시와가치설계")],
    )
    facts = profile_facts(profile)
    assert facts["courses"] == [{"code": "GE1394", "name": "AI리터러시와가치설계"}]
    assert set(facts) == {
        "realName",
        "introduction",
        "fieldCodes",
        "roleCodes",
        "skillCodes",
        "experienceState",
        "experienceBody",
        "weeklyAvailabilityCode",
        "courses",
    }
    profile.courses = []
    assert profile_facts(profile)["courses"] == []
