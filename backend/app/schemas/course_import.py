"""학수번호로 통합된 외부 과목 JSON의 입력 형식을 검증한다."""

from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    model_validator,
)

from app.rules.text import normalize_text
from app.schemas.catalogs import CourseCode

CourseText = Annotated[StrictStr, AfterValidator(normalize_text), Field(min_length=1)]


class ImportedCourse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: CourseCode
    name: CourseText
    aliases: list[CourseText]
    departments: list[CourseText]

    @model_validator(mode="after")
    def distinct_values(self) -> Self:
        for values in (self.aliases, self.departments):
            if len(values) != len(set(values)):
                raise ValueError("Catalog values must be distinct")
        return self


class CourseImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1.0"]
    courses: list[ImportedCourse] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_codes(self) -> Self:
        codes = [course.code for course in self.courses]
        if len(codes) != len(set(codes)):
            raise ValueError("Course codes must be distinct")
        return self
