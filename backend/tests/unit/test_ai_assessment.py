"""지원자 평가의 항목 계약과 실제 조회 자료에 연결된 근거만 허용한다."""

from copy import deepcopy
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.assessment import assessment_evidence, build_assessments
from app.agents.tools import SourceTools
from app.agents.types import (
    ApplicantAssessmentPlan,
    RecommendationPlan,
    Reference,
    Resource,
    Selection,
)
from app.schemas.ai import ApplicantAssessment
from app.services.ai import validate_plan
from app.services.ai_sources import SourceReader


def applicant() -> Resource:
    return Resource(
        reference=Reference(
            kind="application", resource_id=uuid4(), fingerprint="a" * 64
        ),
        title="지원자",
        is_demo=False,
        facts={
            "role": "design",
            "message": "사용자 인터뷰에 참여하고 싶어요.",
            "profile": {
                "roleCodes": ["design"],
                "skillCodes": ["ui_ux"],
                "experienceState": "provided",
                "experienceBody": "동아리 프로젝트에서 화면을 설계했어요.",
                "weeklyAvailabilityCode": "from_5_to_10",
                "introduction": "함께 만들고 싶어요.",
                "courses": [{"code": "GE1394", "name": "AI리터러시"}],
                "privateToken": "never-expose",
            },
            "team": {"roleCodes": ["design"], "introduction": "서비스를 만들어요."},
        },
    )


def assessment_data() -> dict[str, Any]:
    return {
        "criteria": [
            {
                "key": key,
                "score": None,
                "informationStatus": "insufficient",
                "summary": "추가 확인이 필요해요.",
                "evidence": [],
            }
            for key in ("role", "skills", "experience", "availability")
        ],
        "questions": ["어떤 역할을 맡고 싶나요?"],
    }


def output_data(source: Resource) -> dict[str, Any]:
    assessment = assessment_data()
    for criterion in assessment["criteria"]:
        criterion["evidenceRefs"] = criterion.pop("evidence")
    return {
        "summary": "등록 정보와 추가 확인 사항을 함께 검토해 주세요.",
        "assessments": [{"key": source.reference.key, **assessment}],
    }


def test_recommendation_bounds_evaluated_subset_without_claiming_all_observed() -> None:
    resources = [applicant() for _ in range(5)]
    for resource in resources:
        resource.is_selection_candidate = True
    reader = Mock(spec=SourceReader)
    reader.context = Mock(purpose="applicant_recommendation")
    sources = SourceTools(reader, max_sources=30, max_calls=8)
    sources.observed = {resource.reference.key: resource for resource in resources}
    choices = [
        Selection(key=resource.reference.key, reason="이번 검토 후보", evidence=[])
        for resource in resources
    ]
    plan = RecommendationPlan(
        intent="recommend", selections=choices[:3], guidance="안내"
    )
    assert validate_plan(plan, sources) == resources[:3]
    plan.selections = choices[:4]
    with pytest.raises(ValueError):
        validate_plan(plan, sources)
    output = output_data(resources[0])
    output["assessments"] = [
        output_data(resource)["assessments"][0] for resource in resources[:4]
    ]
    with pytest.raises(ValidationError):
        ApplicantAssessmentPlan.model_validate(output)


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "unknown"])
def test_assessment_requires_each_comparable_criterion_once(change: str) -> None:
    value = assessment_data()
    if change == "missing":
        value["criteria"].pop()
    elif change == "duplicate":
        value["criteria"][-1]["key"] = "role"
    elif change == "extra":
        value["criteria"].append(deepcopy(value["criteria"][0]))
    else:
        value["criteria"][0]["key"] = "academic_rank"
    with pytest.raises(ValidationError):
        ApplicantAssessment.model_validate(value)


def test_scored_assessment_and_model_output_require_evidence() -> None:
    value = assessment_data()
    value["criteria"][0].update(score=75, informationStatus="sufficient")
    with pytest.raises(ValidationError):
        ApplicantAssessment.model_validate(value)
    output = output_data(applicant())
    output["assessments"][0]["criteria"][0].update(
        score=75, informationStatus="sufficient"
    )
    with pytest.raises(ValidationError):
        ApplicantAssessmentPlan.model_validate(output)


@pytest.mark.parametrize("score", [0, 5, 25, 50, 75, 95, 100])
def test_scores_accept_only_anchored_integer_steps_and_keep_zero_distinct(
    score: int,
) -> None:
    source = applicant()
    output = output_data(source)
    output["assessments"][0]["criteria"][0].update(
        score=score, informationStatus="sufficient", evidenceRefs=["application.role"]
    )
    result = build_assessments(ApplicantAssessmentPlan.model_validate(output), [source])
    wire = result[source.reference.key].model_dump(mode="json")
    assert wire["criteria"][0]["score"] == score
    assert wire["criteria"][0]["informationStatus"] == "sufficient"
    assert wire["criteria"][1]["score"] is None
    assert wire["criteria"][1]["informationStatus"] == "insufficient"
    assert ApplicantAssessment.model_validate(wire).criteria[0].score == score


@pytest.mark.parametrize("score", [True, False, 75.0, 75.5, "75", -5, 105, 1, 99])
def test_score_rejects_coercions_out_of_range_and_non_five_steps(score: object) -> None:
    value = assessment_data()
    value["criteria"][0].update(
        score=score,
        informationStatus="sufficient",
        evidence=[{"source": "application.role", "text": "디자인"}],
    )
    output = output_data(applicant())
    output["assessments"][0]["criteria"][0].update(
        score=score, informationStatus="sufficient", evidenceRefs=["application.role"]
    )
    with pytest.raises(ValidationError):
        ApplicantAssessment.model_validate(value)
    with pytest.raises(ValidationError):
        ApplicantAssessmentPlan.model_validate(output)


@pytest.mark.parametrize(
    ("score", "status"),
    [(None, "sufficient"), (0, "insufficient"), (75, "insufficient")],
)
def test_information_status_and_nullable_score_must_agree(
    score: int | None, status: str
) -> None:
    value = assessment_data()
    value["criteria"][0].update(
        score=score,
        informationStatus=status,
        evidence=[{"source": "application.role", "text": "디자인"}],
    )
    output = output_data(applicant())
    output["assessments"][0]["criteria"][0].update(
        score=score, informationStatus=status, evidenceRefs=["application.role"]
    )
    with pytest.raises(ValidationError):
        ApplicantAssessment.model_validate(value)
    with pytest.raises(ValidationError):
        ApplicantAssessmentPlan.model_validate(output)


@pytest.mark.parametrize("field", ["score", "informationStatus"])
def test_nullable_score_and_information_status_are_required(field: str) -> None:
    value = assessment_data()
    del value["criteria"][0][field]
    output = output_data(applicant())
    del output["assessments"][0]["criteria"][0][field]
    with pytest.raises(ValidationError):
        ApplicantAssessment.model_validate(value)
    with pytest.raises(ValidationError):
        ApplicantAssessmentPlan.model_validate(output)


def test_obsolete_categorical_state_is_rejected() -> None:
    value = assessment_data()
    value["criteria"][0]["state"] = "supported"
    with pytest.raises(ValidationError):
        ApplicantAssessment.model_validate(value)


@pytest.mark.parametrize("blank", [" ", "\t\n", "\u3000", "\ufeff \ufeff"])
@pytest.mark.parametrize("field", ["summary", "question"])
def test_whitespace_assessment_text_is_rejected_before_completion(
    blank: str, field: str
) -> None:
    value = assessment_data()
    output = output_data(applicant())
    if field == "summary":
        value["criteria"][0]["summary"] = blank
        output["assessments"][0]["criteria"][0]["summary"] = blank
    else:
        value["questions"] = [blank]
        output["assessments"][0]["questions"] = [blank]
    with pytest.raises(ValidationError):
        ApplicantAssessment.model_validate(value)
    with pytest.raises(ValidationError):
        ApplicantAssessmentPlan.model_validate(output)


@pytest.mark.parametrize("blank", [" ", "\t\n", "\u3000", "\ufeff \ufeff"])
def test_whitespace_assessment_overview_is_not_a_completed_answer(blank: str) -> None:
    output = output_data(applicant())
    output["summary"] = blank
    with pytest.raises(ValidationError):
        ApplicantAssessmentPlan.model_validate(output)


@pytest.mark.parametrize(
    "changes",
    [
        {"questions": ["확인"] * 4},
        {"questions": ["가" * 201]},
        {"questions": [""]},
        {"score": 90},
    ],
)
def test_assessment_bounds_questions_and_rejects_total_scores(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ApplicantAssessment.model_validate({**assessment_data(), **changes})


def test_assessment_evidence_is_taken_from_registered_source_values() -> None:
    source = applicant()
    output = output_data(source)
    criterion = output["assessments"][0]["criteria"][2]
    criterion.update(
        score=75,
        informationStatus="sufficient",
        summary="지원자가 관련 경험을 등록했어요.",
        evidenceRefs=["profile.experienceBody", "profile.courses:GE1394"],
    )
    result = build_assessments(ApplicantAssessmentPlan.model_validate(output), [source])
    evidence = result[source.reference.key].criteria[2].evidence
    assert evidence[0].source == "profile.experienceBody"
    assert "동아리 프로젝트에서 화면을 설계했어요." in evidence[0].text
    assert evidence[1].source == "profile.courses"
    assert "GE1394" in evidence[1].text and "AI리터러시" in evidence[1].text
    assert "never-expose" not in str(assessment_evidence(source))
    assert "privateToken" not in str(assessment_evidence(source))


@pytest.mark.parametrize(
    "reference",
    [
        "profile.skillCodes:programming",
        "profile.courses:UNKNOWN",
        "profile.privateToken",
        f"application:{uuid4()}:profile.skillCodes:ui_ux",
    ],
)
def test_model_cannot_cite_unregistered_or_private_evidence(reference: str) -> None:
    source = applicant()
    output = output_data(source)
    output["assessments"][0]["criteria"][1].update(
        score=75, informationStatus="sufficient", evidenceRefs=[reference]
    )
    with pytest.raises(ValueError):
        build_assessments(ApplicantAssessmentPlan.model_validate(output), [source])


def test_team_requirements_cannot_be_used_as_scored_applicant_skills() -> None:
    source = applicant()
    output = output_data(source)
    output["assessments"][0]["criteria"][1].update(
        score=75, informationStatus="sufficient", evidenceRefs=["team.roleCodes:design"]
    )
    with pytest.raises(ValueError):
        build_assessments(ApplicantAssessmentPlan.model_validate(output), [source])


@pytest.mark.parametrize("missing", ["team.introduction", "application.message"])
def test_availability_score_needs_team_requirement_and_applicant_allocation(
    missing: str,
) -> None:
    source = applicant()
    source.facts["message"] = "이 팀에 주 5시간 참여할 수 있어요."
    source.facts["team"] = {
        "roleCodes": ["design"],
        "introduction": "주 5시간 참여할 디자이너를 찾아요.",
    }
    output = output_data(source)
    refs = [
        "profile.weeklyAvailabilityCode",
        "team.introduction",
        "application.message",
    ]
    criterion = output["assessments"][0]["criteria"][3]
    criterion.update(score=100, informationStatus="sufficient", evidenceRefs=refs)
    assert (
        build_assessments(ApplicantAssessmentPlan.model_validate(output), [source])[
            source.reference.key
        ]
        .criteria[3]
        .score
        == 100
    )
    criterion["evidenceRefs"] = [ref for ref in refs if ref != missing]
    with pytest.raises(ValueError):
        build_assessments(ApplicantAssessmentPlan.model_validate(output), [source])


def test_zero_score_cannot_use_missing_skill_evidence() -> None:
    source = applicant()
    output = output_data(source)
    output["assessments"][0]["criteria"][1].update(
        score=0,
        informationStatus="sufficient",
        evidenceRefs=["application.role"],
    )
    with pytest.raises(ValueError):
        build_assessments(ApplicantAssessmentPlan.model_validate(output), [source])


@pytest.mark.parametrize("change", ["unknown", "missing", "duplicate"])
def test_model_assessments_cover_only_each_selected_applicant(change: str) -> None:
    source = applicant()
    output = output_data(source)
    if change == "unknown":
        output["assessments"][0]["key"] = f"application:{uuid4()}"
    elif change == "missing":
        output["assessments"] = []
    else:
        output["assessments"].append(deepcopy(output["assessments"][0]))
    with pytest.raises(ValueError):
        build_assessments(ApplicantAssessmentPlan.model_validate(output), [source])
