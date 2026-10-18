# 기능 명세 인덱스

이 폴더는 서비스 동작·정책·예외·완료 조건을 관리합니다. 스프린트 1 기획 원문을 도메인별로 정리했으며, [전체 범위와 원문 대응](sprint-1.md)에서 문서별 책임을 확인합니다. 정책 합의는 각 명세의 검토 PR, 구현 여부는 상태와 구현 PR로 확인합니다. 문서 게시만으로 구현 완료를 뜻하지 않습니다.

## 작업별 읽기

현재 작업의 시작 문서를 고르고, 추가 참조는 해당 조건에 맞는 절만 읽습니다. 링크를 모두 재귀적으로 읽지 않습니다. 원문의 미정 사항은 담당 명세에 남기고, 같은 정책을 다른 문서에 다시 정의하지 않습니다.

| 작업 | 시작 문서 | 추가로 읽는 조건 |
| --- | --- | --- |
| 스프린트 범위·일정·주요 화면·시연 확인 | [스프린트 1](sprint-1.md) | 상세 정책은 해당 영역의 명세만 선택 |
| 자체 가입·로그인·시연 계정·향후 소셜 연결 | [가입과 로그인](authentication.md) | 인증 정보 공개를 바꾸면 [프로필 공개 범위](profile.md#visibility) |
| 프로필 입력·사람 탐색·공개·포트폴리오 | [프로필](profile.md) | 선택지를 바꾸면 [공통 선택지](profile-options.md#choices), 학사 입력이면 [학사 선택 흐름](academic-structure.md#selection-flow) |
| 분야·역할·역량·시간 선택지 | [프로필 선택지](profile-options.md) | 필수 여부를 바꾸면 [프로필 입력 항목](profile.md#fields) |
| 대학·학부·전공 목록 정비 | [학사 구조](academic-structure.md) | 코드 추가·통합·폐지 시 [공통 데이터 관리](profile-options.md#catalog-management) |
| 공고 탐색·수집·등록·공개 조건·마감 | [공모전 공고](contests.md) | 추천을 바꾸면 [추천 매칭](matching.md), 공고 변경의 지원 영향은 [팀 모집과 지원](team-recruitment.md) |
| 팀 생성·모집·지원·취소·선발·팀 공간 | [팀 모집과 지원](team-recruitment.md) | LLM 추천은 [추천 매칭](matching.md), 열람 권한은 [프로필 공개 범위](profile.md#visibility) |
| AI 자연어 탐색·LLM 추천·근거·미정 내부 설계 | [추천 매칭](matching.md) | 입력 분류는 [선택지](profile-options.md), 실제 지원자 상태는 [팀 모집과 지원](team-recruitment.md#states) |
| 서비스 알림함·읽음 상태·상태별 이동 | [서비스 알림](notifications.md) | 원래 지원·선발 상태는 [팀 모집과 지원](team-recruitment.md), 공개 범위는 [프로필](profile.md#visibility) |

## 작성과 검토 안내

| 작업 | 문서 |
| --- | --- |
| 기획 관점에서 내용 정리 | [기능 명세 작성하기](../collaboration/writing-specs.md) |
| GitHub 웹에서 작성·수정 | [웹 수정과 PR 안내](../collaboration/editing-docs.md) |
| 새 명세 작성 | [명세 템플릿](../templates/spec.md) |
| 명세 검토와 개발 시작 | [팀 작업 흐름](../development/workflow.md) |
| 초기 실행 기반의 범위 | [구조와 스캐폴딩](../development/architecture.md) |

새 명세는 작업별 읽기 표에 추가합니다. 구현 상태는 해당 명세에서 관리하고 여기에는 중복하지 않습니다. API·DB 상세 설계는 명세 합의 이후 개발 계획에서 다룹니다. 완료 조건은 문서와 AC 번호를 함께 참조하며, 명세 합의만으로 체크하지 않습니다.
