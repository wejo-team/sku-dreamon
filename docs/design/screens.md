# 화면과 기능 명세

경로의 공통 접두사는 `/design-preview`이며 로컬 기준 주소는 `http://127.0.0.1:5174`입니다. 경로의 모양이 제품의 최종 URL을 확정하지는 않습니다. 전체 화면 연결은 [라우트 원본](../../design-reference/src/pages/DesignPreviewPage.tsx), 공통 상단·하단 탐색은 [PreviewShell](../../design-reference/src/features/design-preview/PreviewShell.tsx)에서 확인합니다.

## 화면별 참조

| 화면·경로 | 코드 원본 | 구현할 정책·완료 조건 |
| --- | --- | --- |
| 로그인·가입 `/login`, `/signup` | [AccountPages](../../design-reference/src/features/design-preview/AccountPages.tsx) | [인증 AC-04~13](../specs/authentication.md#acceptance-criteria): 자체 로그인·교내 미인증·로그인 후 행동·접근 권한. 레퍼런스 로그인은 모의 동작 |
| 공모전 탐색 `/explore` | [ExplorePages](../../design-reference/src/features/design-preview/ExplorePages.tsx), [ExploreFilters](../../design-reference/src/features/design-preview/ExploreFilters.tsx) | [공고 명세](../specs/contests.md): 제목·분야·마감·공개 정보, 검색·필터·빈 결과. 분야는 아이콘으로 여는 Drawer에서 선택·적용 |
| 공모전 상세 `/contests/:contestId` | [ExplorePages](../../design-reference/src/features/design-preview/ExplorePages.tsx) | [공고 공개·참가·마감 정책](../specs/contests.md): 원문·참가 방식·인원·일정·제출물·미확인 정보, 관련 팀·팀 만들기 연결 |
| 팀 탐색 `/explore?tab=teams` | [ExplorePages](../../design-reference/src/features/design-preview/ExplorePages.tsx) | [팀 AC-01](../specs/team-recruitment.md#acceptance-criteria): 모집 역할·정원·상태·공모전별 탐색 |
| 공개 모집글 `/teams/:teamId` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 AC-03~07·15·18·26](../specs/team-recruitment.md#acceptance-criteria): 지원·필수 프로필 보완·메시지·마감·중복·취소 후 재지원 |
| 팀 만들기 `/teams/new` | [CreateTeamPage](../../design-reference/src/features/design-preview/CreateTeamPage.tsx), [ContestPicker](../../design-reference/src/features/design-preview/ContestPicker.tsx) | [팀 AC-02·13·16·22~24](../specs/team-recruitment.md#acceptance-criteria): 공모전 검색 선택, 목표·역할·팀장 포함 정원·마감·공식 인원 범위·개인 전용 준비 팀 |
| 워크스페이스 `/workspace` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 공간 접근](../specs/team-recruitment.md#team-workspace-access): 본인이 팀장이거나 현재 확정 팀원인 팀과 빈 상태. 제목 옆 내 지원·팀 만들기 아이콘, 팀 카드 전체를 눌러 팀 공간 이동 |
| 내 지원 `/workspace?view=applications` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 AC-04·17~18](../specs/team-recruitment.md#acceptance-criteria): 현재 지원 상태·선발 후 취소·자리 반환·재지원 |
| 팀 공간 `/teams/:teamId?view=space` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 AC-09·13·20·25](../specs/team-recruitment.md#acceptance-criteria): 팀장·현재 팀원만 접근, 확정 인원·남은 자리·공고·모집 상태 |
| 지원자 관리 `/teams/:teamId?view=applicants` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 AC-05·14·16](../specs/team-recruitment.md#acceptance-criteria): 해당 팀장만 실제 지원자 검토·선발. 선발 성공 즉시 팀원 확정 |
| 지원자 검토 `/applicants/:applicantId` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [프로필 공개 정책](../specs/profile.md#visibility), [팀 선발 정책](../specs/team-recruitment.md#membership-capacity): 현재 공개된 경험·역량·소개·동의한 포트폴리오 |
| 내 프로필 `/profile` | [AccountPages](../../design-reference/src/features/design-preview/AccountPages.tsx), [ProfileFields](../../design-reference/src/features/design-preview/ProfileFields.tsx) | [프로필 AC-01·06·20~25](../specs/profile.md#acceptance-criteria): 학사·역량·경험·시간 입력, 단일 포트폴리오 URL·제목, 공개 스위치, 선택형 마스코트 이미지 |
| 본인 공개 화면 확인 `/profile/public` | [AccountPages](../../design-reference/src/features/design-preview/AccountPages.tsx) | [사람 탐색과 공개 설정](../specs/profile.md#people-directory): 본인이 설정한 공개 결과 확인 |
| 사람 탐색·상세 `/explore?tab=people`, `/people/:personId` | [ExplorePages](../../design-reference/src/features/design-preview/ExplorePages.tsx) | [프로필 AC-23~24](../specs/profile.md#acceptance-criteria): 로그인과 탐색 공개 동의, 항목별 공개. 지원자 관계와 구분 |
| AI `/ai` | [AiChatPage](../../design-reference/src/features/design-preview/AiChatPage.tsx) | [LLM 추천 AC-16~24](../specs/matching.md#acceptance-criteria): 자연어 입력·결과·후속 조건·중단·실패·재시도·빈 결과. 실제 LLM은 미구현 |
| 상단 알림함 · 별도 경로 없음 | [Notifications](../../design-reference/src/features/design-preview/Notifications.tsx) | [알림 AC-01~06](../specs/notifications.md): 읽음·미읽음·모두 읽음·소유 관계·관련 화면 이동 |
| 시작·없는 경로 `/loading`, 정의되지 않은 주소 | [LoadingPage](../../design-reference/src/features/design-preview/LoadingPage.tsx), [라우트](../../design-reference/src/pages/DesignPreviewPage.tsx) | 시작 안내와 찾을 수 없는 대상·경로에서 탐색으로 돌아가기 |

UI에서 확인할 수 있는 흐름과 명세 전체의 구현 완료는 다릅니다. 특히 API 오류·서버 권한·동시 선발·영구 저장은 레퍼런스의 로컬 상태만으로 검증되지 않습니다.

## 확인할 상태와 연결

| 흐름 | 화면을 검토할 때 함께 확인할 것 |
| --- | --- |
| 탐색 → 상세 → 복귀 | 검색·선택한 탭·필터, 결과 없음, 공고·팀이 없는 주소. 커서 조회·무한 스크롤·이전 스크롤 복원은 현재 제품 계약으로 확정하지 않음 |
| 탐색 필터·정렬·초기화 | 필터 아이콘 → Drawer의 분야/역할 초안 선택 → 적용 시 URL 반영. 취소·Escape·바깥 닫기 시 미적용 선택 제거, 다시 열면 적용값 복원. 팀의 모집중만 조건, 정렬만 변경했을 때도 초기화 아이콘 표시·기본 조건 복원 |
| 탐색 → AI | 공모전·팀 탐색 제목 옆 AI 아이콘으로 이동. 큰 추천 배너 없이 44px 조작 영역·접근성 이름 제공 |
| 워크스페이스 → 내 지원·팀 만들기 | 제목 옆 목록 아이콘의 접근성 이름·title은 `내 지원`, 더하기 아이콘은 `팀 만들기`. 각각 44px 조작 영역을 유지하고 팀 만들기는 녹색 주요 행동으로 표시. 내 지원 화면에서는 해당 아이콘의 `aria-current`와 녹색 선택 상태 확인 |
| 워크스페이스 → 팀 공간 | 카드 전체가 링크이며 접근성 이름은 팀 이름과 `팀 공간으로`를 포함. 카드 안 이동 문구는 생략하고 내 역할·확정 인원 요약과 같은 행의 우하단 화살표로 이동 가능성을 표시. 공개 모집글과 선발 이후의 명시적 `팀 공간으로` 버튼은 유지 |
| 팀 만들기 → 공모전 선택 | Drawer 열기·검색·선택·취소·닫기, 결과가 많을 때 추가 표시, 팀장 포함 총인원 안내와 공식 인원 범위 오류 |
| 프로필 수정 → 저장 | 캐릭터 팝업 선택·취소·프로필 저장, 기본 스콘, 공개 결과·팀 공간에서 같은 이미지 표시, 학사 상위 선택 변경, 경험 미입력/경험 없음 구분, 공개 동의 기본값, URL 삭제·무효화 후 공개 해제, 취소 시 미저장 값 제거 |
| 지원 → 내 지원 | 로그인 안내, 필수 프로필 보완 후 원래 흐름 복귀, 선택 메시지, 중복·마감·정원 부족, 접수 후 현재 지원 표시 |
| 팀장 검토 → 선발 | 해당 팀장 권한, 현재 공개 프로필, 선발 즉시 멤버 반영·남은 자리 감소, 마지막 자리·공모전별 소속 제한 |
| 선발 후 취소 → 재지원 | 팀 공간 접근 종료·자리 반환, 과거 선발 복원 없이 새 지원, 현재 모집 종료·정원 조건 재확인 |
| AI → 추천 카드 → 상세 | 준비 중·중단·오류·재시도·결과 없음, 공개 정보 제한, 다시 돌아왔을 때 대화 유지. 이전 카드 표시·복사에도 현재 공개 범위·모집 상태·마감·정원 반영, 입력창과 하단 영역의 겹침 |
| 알림 → 관련 화면 | 알림함 열기만으로 읽음 처리하지 않음, 개별/모두 읽음, 빈 상태, 비로그인에 개인 항목 비노출. 읽음 실패 시 개수와 미읽음 상태 유지, 같은 동작 재시도 후 관련 화면 이동 |

반응형 확인은 320px·390px·430px 모바일 폭을 기준으로 합니다. 팝업 포커스·닫기·키보드, 긴 제목·설명, 큰 글꼴, 안전 영역과 세로 스크롤을 함께 검토합니다. 테스트 결과·스크린샷은 검증한 커밋과 함께 PR에 연결합니다.

키·값 정보는 공모전 카드·상세, 팀 목록·공간, 내 프로필·공개 프로필·지원자 검토에서 같은 [정보 계층](tokens.md)을 사용합니다. 워크스페이스 팀 카드는 내 역할과 확정 인원/정원으로 요약하고, 중복되는 `팀장 포함 총 N명` 안내는 생략합니다. 요약 옆 화살표는 별도 버튼이 아니며 카드 링크의 일부입니다. 팀 만들기·모집 상세의 정원 안내와 팀장 포함 정원 계산 정책은 유지합니다.

<a id="remaining-decisions"></a>

## 남은 정책과 구현 결정

아래 항목은 기존 미정 정책을 임의의 UI 동작으로 확정하지 않기 위해 구분합니다. 실제 제품 개발 전에 담당 명세의 결정을 갱신합니다.

| 항목 | 결정 원본 |
| --- | --- |
| LLM 모델·제공자·검색·실행·검증·API·저장·캐시·운영 제한 | [MATCH-12](../specs/matching.md#open-questions) |
| 비공개 정보의 모델 전송·추천 사용, 대화 보존·삭제·철회 후 재노출 방지 | [MATCH-10·13](../specs/matching.md#open-questions) |
| 미확인 자격의 실제 접수, 상태별·마감 후 기존 지원자 추천 | [MATCH-01·08](../specs/matching.md#open-questions), [TEAM-06](../specs/team-recruitment.md#open-questions) |
| 계정 탈퇴의 세션·열람 효력·보존·복구, 조건부 학사 필수 기준 | [PROFILE-03·04](../specs/profile.md#open-questions) |
| 미선발 처리·선발 취소·팀장 위임·모집 재개·모집 정보 수정 범위 | [TEAM-02~08](../specs/team-recruitment.md#open-questions) |
| 운영자 공고 수집·검수·등록 도구, 공고 요약 포함 여부, 날짜만 있는 마감 시각 | [공고 미정 사항](../specs/contests.md#open-questions) |
| 실제 학사 운영 목록·코드·선택지 보충 설명·경험 분류 | [학사 명세](../specs/academic-structure.md), [선택지 미정 사항](../specs/profile-options.md#open-questions) |
| 로그인 세션·보안·복구 세부 | [인증 미정 사항](../specs/authentication.md#open-questions) |
| 알림 저장·중복·기기 동기화·보존 | [알림 미정 사항](../specs/notifications.md) |

팀장이 선발하면 즉시 팀원 확정, 팀장 포함 총 정원, 선발 시 자리 차감, 취소 후 자리 반환·현재 조건에 따른 즉시 재지원은 이미 정해진 정책입니다. 이를 별도 수락 대기나 새 TBD로 되돌리지 않습니다.

## 재현 경로

- `/explore?q=로컬`: 이미지가 없는 공모전의 스콘 기본 커버. 공모전 선택창과 AI 공모전 추천에도 같은 fallback을 적용하며 이미지 로드 실패도 처리.
- `/explore?sort=deadline`: 마감 임박순만 적용된 상태에서 초기화 아이콘 확인. 필터 Drawer에서 분야 선택·취소·적용·다시 열기 확인.
- `/contests/archive`: 마감 공고 읽기 전용 상세·원문 링크.
- `/ai?scenario=error`: 첫 응답 실패 후 같은 요청 재시도. `마케팅 역할 사람 찾아줘`로 결과 없음 확인.
- `/explore?scenario=notification-error`: 로그인한 상태에서 첫 읽음 처리 실패·재시도.
- `/teams/greenwave?view=applicants`: 팀장 검토·선발·확정 팀원.
- `/workspace?view=applications`: 기존 선발된 로컬 크루 지원 취소·접근 종료 확인.
- `/reference/notices/campus`, `/reference/portfolios/seoyeon`: 실제 기관·개인 사이트를 대신하는 로컬 링크 목적지.

모든 경로에 `/design-preview` 접두사를 붙입니다. 날짜는 레퍼런스의 수명이 지나도 검토할 수 있도록 2026-10-18에 고정한 예시이며 운영 마감 시각 정책이 아닙니다. 모집 종료 후 기존 지원자의 선발·추천은 정책 TBD이므로 이 레퍼런스에서 모델링하지 않습니다. 신규 지원의 마감 제한과 구분해 구현해야 합니다.
