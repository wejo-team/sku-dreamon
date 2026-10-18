# 프로토타입 v11 기능·명세 대조

2026-10-19 기준 배포된 공식 디자인의 적용 기능을 담당 명세와 연결한 검증 기록입니다. 정책 원본은 각 기능 명세이며, 이 문서는 확인한 버전·화면 범위·남은 차이를 관리합니다. **현재 화면이 있다는 사실과 실제 제품 구현 완료를 구분합니다.** 제품 명세의 구현 상태와 완료 조건 체크는 변경하지 않습니다.

## 대조 기준과 원본

| 대상 | 확인한 버전·근거 |
| --- | --- |
| 공유 프로토타입 | [GPT Sites 탐색 화면](https://wejo-team-review-20261018.pjhdye.chatgpt.site/design-preview/explore), 배포 성공한 **v11** |
| 배포 소스 커밋 | `08e020033fb9a9c8f3ee25e07a0c13be385ac94c` — Sites 저장 버전의 소스와 로컬 배포 체크아웃 HEAD 일치 |
| 저장소 디자인 원본 | [디자인 커밋 `030d2df`의 design-reference/][reference] — 배포 소스와 추적 파일 94개의 바이트가 모두 같음 |
| 선행 정책 | [PR #75](https://github.com/wejo-team/sku-dreamon/pull/75)의 전체 프로필 공개·비공개와 AI 로그인 전용 정책. 이 문서 작성 시 병합 전 |
| 디자인 PR | [PR #74](https://github.com/wejo-team/sku-dreamon/pull/74). 이 문서 작성 시 병합 전이며 정책 PR과 별도 검토 |
| 시각·실행 인계 | [화면별 참조][screens], [색상·컴포넌트][tokens], [자산 출처][assets], [실행·개발 인계][handoff] |

프론트엔드 개발자는 저장소의 디자인 원본과 담당 기능 명세를 함께 참조합니다. 공유 사이트가 이후 변경되더라도 이 기록은 위 커밋과 v11에 대한 결과입니다. 디자인 앱이 아직 이 문서 PR의 base에 없으므로 링크는 변경 가능한 브랜치 대신 확인한 커밋에 고정했습니다. 이 문서 PR에는 앱 코드·이미지·의존성·CI 변경을 포함하지 않습니다.

<a id="feature-map"></a>

## 화면별 적용 기능과 명세

아래 경로에는 공통으로 `/design-preview`가 붙습니다. 제품의 최종 URL·API 계약을 확정하는 표는 아닙니다. `화면 일치`는 관찰한 UI·로컬 상태가 문서의 해당 동작과 맞는다는 뜻이며 서버 구현·모든 AC 통과를 뜻하지 않습니다.

| 화면·진입 | 현재 적용된 기능 | 담당 명세와 대조 결과 |
| --- | --- | --- |
| 시작 `/`, `/loading` · 공통 탐색 | 로고·SVG 서비스명, 시작 후 탐색 이동, 하단 탐색·AI·워크스페이스·프로필, 상단 로고 탐색 이동·알림. 로그인/가입은 탐색 복귀 링크, 루트 중복 제목 생략·접근성 제목 유지 | [스프린트 화면](sprint-1.md#screens), [브랜딩](../branding.md). 화면 일치. 시작 지연은 모의 표현 |
| `/login`, `/signup` | 아이디·비밀번호 입력, 보기/숨기기, 빈값·로그인 실패 안내, 내부 목적지 복귀, 가입·로그인 간 이동, 가입 완료 후 로그인 연결 | [인증](authentication.md#access-policy). 화면 일치; 실제 계정 생성·세션은 미구현 |
| 내 프로필의 학교 인증 배지 | 빨간 `교내 미인증`을 누르면 미제공 기능 안내 팝업. 상시 안내문 생략. 파란 인증 상태 스타일은 준비만 됨 | [인증 의미](authentication.md#verification-meaning). 학교 인증 제공·인증 완료 계정은 없음 |
| `/explore` 공모전 | 검색, 분야 필터 팝업의 초안·적용·취소, 등록순·마감 임박순, 초기화 아이콘, 결과 수·빈 결과. 왼쪽 세로 포스터·D-day, 오른쪽 제목→분야→주최자, 우하단 팀 아이콘·숫자, 이미지 실패 시 기본 커버, 전체 카드 클릭 | [공고](contests.md). 간결 카드·필터 화면 일치. 모집 중 집계 차이는 D-01 |
| `/explore?tab=teams` | 검색·역할·모집중만·공모전 조건, 팀 카드와 상태 배지, 조건 초기화, AI 진입 | [팀 탐색](team-recruitment.md). 상태 기준 필터와 실제 지원 가능 여부 차이는 D-01 |
| `/explore?tab=people`, `/people/:personId` | 로그인 안내, 공개 사용자만 검색·역할 필터·상세, 검색창 AI 아이콘. 비공개·없는 사용자 직접 접근 제한 | [사람 탐색](profile.md#people-directory). 전체 공개·지원 팀장 예외와 구분해 화면 일치 |
| `/contests/:contestId` | 주최자·참가 대상·방식·공식 인원·접수 일정·제출물·원문, 미확인 항목, 마감 읽기 전용, 개인 전용 준비 팀 안내, 관련 팀·팀 만들기·AI 연결 | [공고 공개·참가·마감](contests.md). 상세 정보는 유지되며 목록에서만 대상·정확한 날짜 요약 생략 |
| `/teams/new` | 로그인, 공모전 검색 팝업·추가 표시·선택, 이름·목표·역할·총 정원·모집 기한, 오류 안내, 공모전별 소속 제한, 공식 인원 범위, 생성 후 이동 | [팀 생성](team-recruitment.md). 로컬 흐름 일치; 현재 입력 길이·기준 날짜는 모의 제한으로 분리 |
| 공개 `/teams/:teamId` | 모집 역할·정원·기한·공모전 확인, 로그인·필수 프로필 보완, 역할·선택 메시지 입력, 제출 전 지원 팀장 전체 프로필 공개 안내, 중복·마감·정원 차단 | [지원](team-recruitment.md), [지원 전 프로필](profile.md#before-application). 로컬 흐름 일치 |
| `/workspace`, `?view=applications` | 내 팀·내 지원 전환, 팀 만들기 아이콘, 역할·확정 인원, 녹색 모집 중/회색 마감 배지, 전체 팀 카드 이동, 지원 결과·취소·재지원 | [팀 상태·취소](team-recruitment.md). 중복 `팀장 포함 총 N명` 생략. 본인 메시지 재열람은 D-02 |
| `/teams/:teamId?view=space` | 팀장·현재 확정 팀원만 접근, 공모전 정보·팀원·정원·모집 상태, 팀장의 모집 마감 확인, 지원 취소 뒤 접근 종료 | [팀 공간](team-recruitment.md#team-workspace-access). 로컬 접근·모집 흐름 일치; 별도 매칭 상태는 D-06 |
| `/teams/:teamId?view=applicants`, `/applicants/:applicantId` | 팀장만 지원자 목록·상세 확인, 지원 메시지·전체 현재 프로필, 선발 확인·즉시 팀원 확정·자리 감소·마지막 자리 제한 | [선발·정원](team-recruitment.md#membership-capacity), [프로필 예외](profile.md#visibility). 로컬 흐름 일치. AI 검토 도움은 D-03 |
| `/profile` 보기·편집 | 상단 수정·공개 상태·미리보기 조작, 실명·학사·분야·역할·역량·경험·소개, 경험 미입력/없음/작성, 필수값·URL 검증, 저장·편집 취소·로그아웃 | [프로필 필드](profile.md#fields), [학사](academic-structure.md). 입력 흐름 일치; 운영 학사 목록·조건부 필수 기준은 TBD |
| 공개 스위치·`/profile/public` | 기본 비공개, 양방향 설명 팝업·확인/취소, 전체 등록 항목 단위 전환, 본인 공개 화면 확인. 비공개도 지원받은 팀장에게 전체 열람 | [공개 정책](profile.md#visibility). 화면 일치; 항목별·포트폴리오별 공개 설정 없음 |
| 프로필 이미지 팝업 | 기본 스콘·파워프렌즈 5종, 작은 설명, 선택·적용·취소와 편집 저장, 기존 이미지 유지 | [프로필](profile.md). 캐릭터 선택 화면 일치; 파일 업로드 없음 |
| 활동 가능 시간·포트폴리오 | 요일·3시간 구간 선택 팝업, 초안 적용/취소/지우기, 프로필 저장, 단일 HTTP(S) URL·선택 제목·삭제·열기 | [선택지](profile-options.md), [포트폴리오](profile.md#portfolio). 화면 일치; 공개 범위는 전체 프로필 상태를 따름 |
| `/ai` 및 검색창 AI 아이콘 | 로그인 전용, 시작 예시·자연어 입력·후속 질문·추천 카드·상세 복귀, 준비·중단·실패·재시도·복사, 새 대화 초기화, 탭 간 현재 대화 유지, 로그아웃 시 대화·초안 제거 | [LLM 추천](matching.md). 대화 UI 일치; 실제 LLM·지원자 요청은 미구현, 추천 대상 판정은 D-05. 과거 대화 목록·기록 조회는 제공하지 않음 |
| 상단 알림함 | 로그인 안내, 미읽음 배지·전체/읽지 않음·개별/모두 읽음·빈 상태, 읽음 성공 후 관련 화면 이동, 실패 시 유지·재시도 | [알림](notifications.md). 로컬 흐름 일치; 브라우저 뒤로 닫기는 D-04 |
| `/reference/notices/:id`, `/reference/portfolios/:id`, 없는 주소 | 예시 원문·포트폴리오 목적지, 없는 페이지·대상 안내 및 가능한 복귀 링크 | [시연 범위](sprint-1.md#web-demo). 내부 예시 페이지이며 실제 주최 기관·개인 포트폴리오 연동이 아님 |

현재 카드의 흰 기본 면·녹색 hover/포커스/누름, 선택 탭의 녹색, 정보 키와 값의 대비, 팝업·아이콘의 접근성 이름·터치 영역은 [스타일 원본][tokens]을 따릅니다. 정책 문서에 별도 색상 수치를 복제하지 않습니다.

<a id="known-differences"></a>

## 남아 있는 차이

**문서와 v11이 모든 항목에서 완전히 일치하는 것은 아닙니다.** 문서만 변경하는 이번 작업에서는 아래 구현 차이를 그대로 공개합니다. 기존 요구를 삭제하거나 제품 구현 완료로 표시해 차이를 숨기지 않습니다.

| ID | 문서의 요구·의미 | v11에서 확인한 차이 | 확인 위치·후속 처리 |
| --- | --- | --- | --- |
| D-01 | 모집 중인 팀 정보와 실제 지원 가능 여부를 일관되게 이해할 수 있어야 함. 지원자 검토 중에도 기한·정원 등 조건을 충족하면 접수 가능 | 공모전 카드의 숫자는 `모집중` 상태만 집계하고 `지원자검토`는 제외. 팀의 `모집중만` 필터와 탐색 카드 배지는 정원·기한을 함께 판정하지 않음. 정원에 도달한 팀도 목록에는 `모집중`으로 남을 수 있으며 상세에서는 접수 조건을 다시 검사 | [탐색 코드][explore]의 `matchedTeams`·카드 집계와 [지원 판정][team-state]. 수치·필터를 ‘현재 지원 가능한 팀 수/목록’으로 해석하지 않음. 제품 구현에서 표시 의미와 조건을 함께 정리 |
| D-02 | [지원 메시지](team-recruitment.md#application-message)는 본인·지원받은 팀장만 확인 | 팀장은 지원자 상세에서 메시지를 보지만 내 지원 목록에는 본인이 제출한 메시지의 재열람 UI가 없음 | [WorkspacePages][workspace]의 내 지원·지원자 상세. 본인 메시지 재열람을 구현할 때 AC-26 확인 |
| D-03 | [지원자 추천](matching.md)은 팀장 관리에서 요청·갱신하며 실제 데이터와 근거를 사용 | 지원자 상세의 `AI 검토 도움`은 고정 예시 문구. 추천 요청·재요청이나 실제 LLM 실행 기능이 없음 | [WorkspacePages][workspace]의 지원자 상세. AI 채팅의 모의 응답과도 구분; LLM 내부 아키텍처는 TBD 유지 |
| D-04 | [알림 사용자 흐름](notifications.md)의 뒤로 닫기는 현재 화면을 잃지 않고 팝업에서 복귀하는 경험을 요구 | 닫기·바깥 영역·Escape는 제공하지만 브라우저 뒤로가기와 Drawer 상태를 연결하지 않음. 뒤로가기로 팝업만 닫힌다고 보장할 수 없음 | [Notifications][notifications]·[공통 라우트][routes]. 브라우저 뒤로 처리 구현·검증이 필요 |
| D-05 | [추천 대상·제한](matching.md)은 실제 지원·소속·자격 등 현재 조건을 고려해야 함 | 모의 추천은 공고·팀·공개 사람 데이터로 생성하며 현재 지원 이력·내 소속·자격 판정 데이터를 받지 않음. 모집 상태·정원·마감 일부는 검사하지만 중복 지원·본인 팀·이미 소속된 공모전·자격까지 모두 판단하지 않음 | [모의 추천][chat-demo]. 상세에서 실행하는 지원 제한과 추천 후보 판정을 구분. 현재 TBD인 자격 정책을 먼저 확정하지 않음 |
| D-06 | [팀 공간 AC-09](team-recruitment.md#acceptance-criteria)는 모집·매칭 상태 표시를 포함 | 팀 공간에는 모집 상태가 있으나 별도의 매칭 상태 값·표시는 없음 | [팀 공간][workspace]. 매칭 상태의 구체적인 의미·전이는 TEAM-08의 미정 범위로 남기며 현재 구현으로 간주하지 않음 |

390px 로컬 브라우저에서 D-01·02·04를 별도로 재현했습니다. 초기 그린웨이브(2/4명)의 김서연·정수아를 선발해 4/4명이 된 뒤에도 `탐색 → 팀 → 모집중만`에 `모집중 · 4명 활동 중`으로 남고 공모전 카드 팀 수는 1입니다. 내 지원의 초기 로컬 크루 지원 메시지는 목록에 표시되지 않습니다. 워크스페이스에서 탐색으로 이동해 알림을 연 뒤 브라우저 뒤로가기를 누르면 배경은 워크스페이스로 이동하고 알림 팝업은 열린 채 남습니다. D-03·05·06과 `지원자검토` 집계 차이는 코드 대조로 확인했습니다.

학사 상위 선택 변경 시 하위값 초기화, 기타 설명의 선택 입력 등은 레퍼런스에서 관찰한 선택입니다. 운영 목록 검증·학사 정정·세부 필수 규칙은 [학사 미정 사항](academic-structure.md#open-questions), [선택지 미정 사항](profile-options.md#open-questions)의 결정 범위를 유지합니다. 별도 정책 검토 없이 코드에 있는 선택을 모두 확정 요구사항으로 승격하지 않습니다.

<a id="prototype-boundary"></a>

## 모의 구현과 제품 구현의 경계

| 현재 참고 앱 | 실제 제품에서 별도로 구현·검증할 것 |
| --- | --- |
| 로그인 아이디·비밀번호는 모두 `dreamon-demo`인 공개 UI 확인 문자열. 가입은 실제 계정을 생성하지 않음 | 계정 등록·중복·로그인·로그아웃·세션·복구·보안. 학교 인증은 이번 범위 밖 |
| 프로필·팀·지원·알림은 브라우저의 메모리 상태. 새로고침 시 초기 상태로 복귀 | 영구 저장·API 실패·여러 사용자/기기 동기화·서버 권한·세션 만료 |
| 선발·취소·마감·정원은 로컬 상태 전이 | 서버의 동시 선발·정원 초과 방지·소속 중복·저장 실패 원자성 |
| AI는 고정 예시·로컬 분기 응답. 과거 채팅 기록 조회 UI 없음 | LLM 실행·응답 검증·정보 접근·품질. 모델·검색·프롬프트·API·저장·캐시는 TBD이며 과거 기록 조회 제외와 별개 |
| 예시 날짜는 2026-10-18 기준. 입력 길이·대기 시간·후보 수·선택창 더보기 수치는 로컬 표현 | 실제 현재 시각·마감 시간대·입력 제한·조회 계약·운영 제한 |
| 공모전 원문·포트폴리오는 일부 내부 예시 목적지 | 실제 외부 URL·원문 유효성·공고 수집/등록/검수·포트폴리오 접근 권한 |

탐색 목록은 현재 메모리 데이터의 검색·필터이며 커서 API·무한 스크롤·페이지네이션은 구현하지 않았습니다. 공모전 선택창의 로컬 더보기는 백엔드 페이징 계약이 아닙니다. 상세 복귀 시 검색·필터 URL은 유지하지만 이전 스크롤 위치 복원은 제공하지 않습니다. [PreviewShell][shell]은 경로 변경 시 스크롤을 위로 이동합니다. 이전 대화의 아키텍처 논의를 현재 제품의 확정·구현 사항으로 기록하지 않습니다.

<a id="verification"></a>

## 수행한 검증

- Sites v11 저장 소스 커밋·배포 성공을 조회하고, 배포 체크아웃과 저장소 디자인 커밋의 추적 파일 94개가 동일함을 비교했습니다.
- 위 버전의 라우트·화면·상태 전이·권한 분기·선택지와 관련 테스트를 담당 명세별로 대조했습니다. 인증·프로필, 공모전·팀, AI·알림은 각각 독립 검토 후 통합했습니다.
- 관심 분야·역할·역량·학적·학년·요일·시간의 7개 선택지 분류와 학사 31행·하위 전공 관계가 문서와 코드에서 일치함을 확인했습니다. 운영 학사 정보의 최신성 검증과는 다릅니다.
- 해당 디자인 소스에서 `npm test`를 실행해 **9개 파일·133개 테스트**가 통과했습니다. 이는 테스트가 다루는 로컬 동작의 결과이며, D-01~06이나 서버 영역까지 검증됐다는 뜻이 아닙니다.
- [기존 브라우저 확인 스크립트][browser-check]를 배포 소스와 동일한 로컬 앱에서 실행했습니다. **320·390·430px**에서 비로그인 공개 범위, 마감 공고, 필터 적용/취소, 카드·기본 이미지, 캐릭터·프로필·팀 만들기, 선발/멤버, AI 재시도, 알림 흐름을 통과했고 가로 넘침·런타임 오류가 없었습니다.
- 이 결과는 원격 배포 화면의 모든 상태를 직접 자동화한 결과가 아닙니다. 배포 소스 일치 확인과 로컬 상호작용 검증을 결합했습니다. 실제 모바일 기기·보조 기술·운영 인증·DB·LLM은 검증 대상이 아닙니다.

문서 변경 시에는 링크·앵커, VitePress 빌드와 생성된 HTML 링크·자산도 검사합니다. 다음 디자인 변경은 기준 커밋·배포 버전·영향받는 대조 행·알려진 차이를 함께 갱신합니다. 이 기록만으로 명세의 AC 체크를 완료 처리하지 않습니다.

[reference]: https://github.com/wejo-team/sku-dreamon/tree/030d2df9761334f7f47f870c1afdf163212be1bc/design-reference
[screens]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/docs/design/screens.md
[tokens]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/docs/design/tokens.md
[assets]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/docs/design/assets.md
[handoff]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/docs/design/handoff.md
[explore]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/design-reference/src/features/design-preview/ExplorePages.tsx
[team-state]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/design-reference/src/features/design-preview/team-state.ts
[chat-demo]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/design-reference/src/features/design-preview/chat-demo.ts
[workspace]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/design-reference/src/features/design-preview/WorkspacePages.tsx
[notifications]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/design-reference/src/features/design-preview/Notifications.tsx
[routes]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/design-reference/src/pages/DesignPreviewPage.tsx
[shell]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/design-reference/src/features/design-preview/PreviewShell.tsx
[browser-check]: https://github.com/wejo-team/sku-dreamon/blob/030d2df9761334f7f47f870c1afdf163212be1bc/design-reference/scripts/reference-check.cjs
