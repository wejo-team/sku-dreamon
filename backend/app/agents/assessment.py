"""평가에 인용할 등록 근거를 만들고 모델의 근거 참조를 검증한다."""

from app.agents.types import ApplicantAssessmentPlan, Resource
from app.rules.catalogs import CatalogCode, RoleCode, SkillCode, WeeklyAvailabilityCode
from app.schemas.ai import (
    ApplicantAssessment,
    AssessmentCriterion,
    AssessmentEvidence,
    AssessmentKey,
    AssessmentSource,
)

_SCORED_SOURCES: dict[AssessmentKey, set[AssessmentSource]] = {
    "role": {"application.role", "profile.roleCodes"},
    "skills": {"profile.skillCodes"},
    "experience": {"profile.experienceBody", "profile.experienceState"},
    "availability": {"profile.weeklyAvailabilityCode"},
}


def assessment_evidence(resource: Resource) -> dict[str, AssessmentEvidence]:
    """빈 항목은 근거로 만들지 않으며 긴 등록 원문은 앞부분만 그대로 인용한다."""
    if resource.reference.kind != "application":
        raise ValueError("지원 자료만 평가할 수 있습니다.")
    profile, team = resource.facts.get("profile"), resource.facts.get("team")
    if not isinstance(profile, dict) or not isinstance(team, dict):
        raise ValueError("지원 자료에 프로필과 팀 정보가 필요합니다.")
    evidence: dict[str, AssessmentEvidence] = {}

    def add(source: AssessmentSource, value: object, suffix: str = "") -> None:
        if isinstance(value, str) and value.strip():
            excerpt = value if len(value) <= 500 else value[:497] + "…"
            evidence[source + suffix] = AssessmentEvidence(source=source, text=excerpt)

    def codes(
        source: AssessmentSource, values: object, enum: type[CatalogCode]
    ) -> None:
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str):
                    add(source, enum(value).display_name, ":" + value)

    role = resource.facts.get("role")
    if isinstance(role, str):
        add("application.role", RoleCode(role).display_name)
    add("application.message", resource.facts.get("message"))
    codes("profile.roleCodes", profile.get("roleCodes"), RoleCode)
    codes("profile.skillCodes", profile.get("skillCodes"), SkillCode)
    codes("team.roleCodes", team.get("roleCodes"), RoleCode)
    add("profile.introduction", profile.get("introduction"))
    add("team.introduction", team.get("introduction"))
    if profile.get("experienceState") == "none":
        add("profile.experienceState", "경험 없음으로 등록했어요.")
    elif profile.get("experienceState") == "provided":
        add("profile.experienceBody", profile.get("experienceBody"))
    availability = profile.get("weeklyAvailabilityCode")
    if isinstance(availability, str):
        add(
            "profile.weeklyAvailabilityCode",
            "주당 "
            + WeeklyAvailabilityCode(availability).display_name
            + " (전체 프로젝트를 합한 자기신고 시간)",
        )
    courses = profile.get("courses")
    if isinstance(courses, list):
        for course in courses:
            if isinstance(course, dict):
                code, name = course.get("code"), course.get("name")
                if isinstance(code, str) and isinstance(name, str):
                    add("profile.courses", f"{code} · {name}", ":" + code)
    return evidence


def build_assessments(
    output: ApplicantAssessmentPlan, resources: list[Resource]
) -> dict[str, ApplicantAssessment]:
    by_key = {resource.reference.key: resource for resource in resources}
    keys = [item.key for item in output.assessments]
    if len(set(keys)) != len(keys) or set(keys) != set(by_key):
        raise ValueError("검증된 지원자와 평가 대상이 일치하지 않습니다.")
    result: dict[str, ApplicantAssessment] = {}
    order: tuple[AssessmentKey, ...] = ("role", "skills", "experience", "availability")
    for item in output.assessments:
        registry = assessment_evidence(by_key[item.key])
        criteria: list[AssessmentCriterion] = []
        for criterion in sorted(
            item.criteria, key=lambda value: order.index(value.key)
        ):
            refs = criterion.evidence_refs
            if len(set(refs)) != len(refs) or any(ref not in registry for ref in refs):
                raise ValueError("등록 자료에 없는 평가 근거입니다.")
            evidence = [registry[ref] for ref in refs]
            if criterion.score is not None and not any(
                entry.source in _SCORED_SOURCES[criterion.key] for entry in evidence
            ):
                raise ValueError(
                    "점수가 있는 항목에는 해당 지원자의 등록 근거가 필요합니다."
                )
            if (
                criterion.key == "availability"
                and criterion.score is not None
                and not {"team.introduction", "application.message"}.issubset(
                    {entry.source for entry in evidence}
                )
            ):
                raise ValueError(
                    "참여시간 점수에는 팀 조건과 지원 메시지도 필요합니다."
                )
            criteria.append(
                AssessmentCriterion(
                    key=criterion.key,
                    score=criterion.score,
                    information_status=criterion.information_status,
                    summary=criterion.summary,
                    evidence=evidence,
                )
            )
        result[item.key] = ApplicantAssessment(
            criteria=criteria, questions=item.questions
        )
    return result
