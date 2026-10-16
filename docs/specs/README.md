# 기능 명세 인덱스

이 폴더는 서비스 동작·정책·예외·완료 조건을 관리합니다. 기획 원문을 도메인별로 이관하고 있으며, 정책 합의는 각 명세의 검토 PR, 구현 여부는 상태와 구현 PR로 확인합니다. 문서 게시만으로 구현 완료를 뜻하지 않습니다.

## 작업별 읽기

현재 작업의 시작 문서를 고르고, 추가 참조는 해당 조건에 맞는 절만 읽습니다. 링크를 모두 재귀적으로 읽지 않습니다. 원문의 미정 사항은 담당 명세에 남기고, 같은 정책을 다른 문서에 다시 정의하지 않습니다.

| 작업 | 시작 문서 | 추가로 읽는 조건 |
| --- | --- | --- |
| 제품 개요(PRD)·스프린트 범위·전체 시연 | [스프린트 1](sprint-1.md) | 제품 가치는 [성과 검토](sprint-1.md#product-validation), 기능별 완료 조건은 [전체 흐름 검증](sprint-1.md#end-to-end)에서 선택 |
| 가입·교내 인증·시연 인증 | [인증](authentication.md) | 인증 정보 공개를 바꾸면 [프로필 공개 범위](profile.md#visibility) |
| 프로필 입력·공개·포트폴리오 | [프로필](profile.md) | 선택지를 바꾸면 [공통 선택지](profile-options.md#choices), 학사 입력이면 [학사 선택 흐름](academic-structure.md#selection-flow) |
| 분야·역할·역량·시간 선택지 | [프로필 선택지](profile-options.md) | 필수 여부를 바꾸면 [프로필 입력 항목](profile.md#fields), 의미·관련도를 바꾸면 [추천 계산](matching.md#processing) |
| 대학·학부·전공 목록 정비 | [학사 구조](academic-structure.md) | 코드 추가·통합·폐지 시 [공통 데이터 관리](profile-options.md#catalog-management) |
| 공고 등록·요약·공개·마감 | [공고](contests.md) | 실제 팀 지원에 영향을 주면 [지원 가능 정책](teams.md#application-rules), 개인화 순위를 바꾸면 [공모전 추천](matching.md#contest-scoring) |
| 팀 생성·지원·선발·팀 공간 | [팀](teams.md) | 공고 조건은 [참가 자격](contests.md#eligibility)·[마감](contests.md#deadlines), 지원자 열람은 [프로필 공개 범위](profile.md#visibility), 순위는 [팀·지원자 추천](matching.md#team-scoring) |
| 추천 계산·설명·갱신 | [추천](matching.md) | 입력 정의를 바꾸면 [선택지](profile-options.md#choices)·[시간 구간](profile-options.md#time-slots), 업무 조건을 바꾸면 [공고 자격](contests.md#eligibility)·[팀 지원](teams.md#application-rules) |

## 작성과 검토 안내

| 작업 | 문서 |
| --- | --- |
| 기획 관점에서 내용 정리 | [기능 명세 작성하기](../collaboration/writing-specs.md) |
| GitHub 웹에서 작성·수정 | [웹 수정과 PR 안내](../collaboration/editing-docs.md) |
| 새 명세 작성 | [명세 템플릿](../templates/spec.md) |
| 명세 검토와 개발 시작 | [팀 작업 흐름](../development/workflow.md) |
| 초기 실행 기반의 범위 | [구조와 스캐폴딩](../development/architecture.md) |

새 명세는 작업별 읽기 표에 추가합니다. 구현 상태는 해당 명세에서 관리하고 여기에는 중복하지 않습니다. API·DB 상세 설계는 명세 합의 이후 개발 계획에서 다룹니다. 완료 조건은 문서와 AC 번호를 함께 참조하며, 명세 합의만으로 체크하지 않습니다.
