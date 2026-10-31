# 화면과 기능 명세

경로의 공통 접두사는 `/design-preview`이며 로컬 기준 주소는 `http://127.0.0.1:5174`입니다. 경로의 모양이 제품의 최종 URL을 확정하지는 않습니다. 전체 화면 연결은 [라우트 원본](../../design-reference/src/pages/DesignPreviewPage.tsx), 공통 상단·하단 탐색은 [PreviewShell](../../design-reference/src/features/design-preview/PreviewShell.tsx)에서 확인합니다.

[선행 문서 PR #93](https://github.com/wejo-team/sku-dreamon/pull/93)과 [#77 최신 결정](https://github.com/wejo-team/sku-dreamon/issues/77#issuecomment-6260435650)의 정책과 [정책 PR #94](https://github.com/wejo-team/sku-dreamon/pull/94)의 [팀장 모집 재개](../specs/team-recruitment.md#recruitment-reopening)·[동시 지원과 폐기](../specs/team-recruitment.md#parallel-applications) 결정을 기준으로 화면을 갱신합니다. 아래 내용은 현재 저장소의 참고 구현과 확인할 동작이며, 서버·실제 AI·영구 저장 또는 배포 검증 완료를 뜻하지 않습니다.

탐색·AI·워크스페이스·내 프로필 보기의 루트 제목은 하단 탐색과 중복되므로 `h1.sr-only`로 유지하고 화면 공간은 사용하지 않습니다. 공모전·팀·지원자 상세 제목과 `프로필 수정` 제목은 표시합니다. 로그인 안내와 필요한 복귀 링크도 유지합니다.

## 화면별 참조

| 화면·경로 | 코드 원본 | 구현할 정책·완료 조건 |
| --- | --- | --- |
| 로그인·가입 `/login`, `/signup` | [AccountPages](../../design-reference/src/features/design-preview/AccountPages.tsx) | [인증 완료 조건](../specs/authentication.md#acceptance-criteria): 아이디 4~24자 ASCII 소문자/숫자 정규화, 비밀번호 NFC 8~128자·가입 시 기호 포함·실시간 조건 표시·공백 보존·보기/숨기기·붙여넣기. 교내 미인증·접근 권한; 실제 계정 발급은 없음 |
| 공모전 탐색 `/explore` | [ExplorePages](../../design-reference/src/features/design-preview/ExplorePages.tsx), [ExploreFilters](../../design-reference/src/features/design-preview/ExploreFilters.tsx) | [공고 명세](../specs/contests.md): 왼쪽 세로 포스터·D-day, 오른쪽 제목·분야·주최자와 우하단 팀 아이콘·모든 연결 팀 수. 카드 전체로 상세 이동. 검색·필터·번호 페이지·빈 결과, 분야는 아이콘으로 여는 Drawer에서 선택·적용 |
| 공모전 상세 `/contests/:contestId` | [ExplorePages](../../design-reference/src/features/design-preview/ExplorePages.tsx) | [공고 공개·참가·마감 정책](../specs/contests.md): 원문·참가 대상·최소/최대 인원·일정·제출물·미확인 정보, 해당 공모전의 팀을 상세 안에 바로 표시. 생성(+)/AI 아이콘, 열린 공고의 빈 팀 안내, 마감 시 생성·AI 숨김 |
| 팀 탐색 `/explore?tab=teams` | [ExplorePages](../../design-reference/src/features/design-preview/ExplorePages.tsx) | [팀 AC-01](../specs/team-recruitment.md#acceptance-criteria): 모집 역할·정원·상태·공모전별 탐색과 번호 페이지 |
| 공개 모집글 `/teams/:teamId` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 AC-03~07·15·18·26](../specs/team-recruitment.md#acceptance-criteria): 지원·필수 프로필 보완·메시지·마감·중복·취소 후 재지원 |
| 팀 만들기 `/teams/new` | [CreateTeamPage](../../design-reference/src/features/design-preview/CreateTeamPage.tsx), [ContestPicker](../../design-reference/src/features/design-preview/ContestPicker.tsx) | [팀 생성·정원 정책](../specs/team-recruitment.md#acceptance-criteria): 공모전 검색 선택, 팀명 2~40자·소개 10~1,000자·역할 1~6개, 모든 팀의 공식 인원 범위. 분야는 공모전 상속, 범위 정원 기본값 없음, 정원 1명은 역할/추가 모집 생략. 준비 모임 예외 없음 |
| 워크스페이스 `/workspace` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 공간 접근](../specs/team-recruitment.md#team-workspace-access): 본인이 팀장이거나 현재 확정 팀원인 팀과 빈 상태. 내 팀·내 지원 콘텐츠 제목과 개수, 작업 아이콘을 한 줄에 배치하고 팀 카드 전체를 눌러 팀 공간 이동 |
| 내 지원 `/workspace?view=applications` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 AC-04·17~18](../specs/team-recruitment.md#acceptance-criteria): 현재 지원 상태·선발 후 취소·자리 반환·재지원, 다른 팀 선발에 따른 폐기 사유·이력 |
| 팀 공간 `/teams/:teamId?view=space` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 AC-09·13·20·25](../specs/team-recruitment.md#acceptance-criteria): 팀장·현재 팀원만 접근, 확정 인원·남은 자리·공고·모집 상태, 팀장 재개 확인·성공·불가 사유 |
| 지원자 관리 `/teams/:teamId?view=applicants` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [팀 AC-05·14·16](../specs/team-recruitment.md#acceptance-criteria): 해당 팀장만 진행 중인 지원(지원 완료·검토 중)을 관리 목록에서 확인하고 검토·선발. 선발 성공 즉시 팀원 확정·같은 공모전의 다른 대기 지원 폐기. 폐기 지원은 이력에 남고 검토 대기 수에서 제외 |
| 지원자 검토 `/applicants/:applicantId` | [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx) | [프로필 공개 정책](../specs/profile.md#visibility), [팀 선발 정책](../specs/team-recruitment.md#membership-capacity): 지원한 팀장이 공개 상태와 관계없이 전체 현재 프로필을 확인. 일반 팀원은 이 예외를 갖지 않음 |
| 내 프로필 `/profile` | [AccountPages](../../design-reference/src/features/design-preview/AccountPages.tsx), [ProfileFields](../../design-reference/src/features/design-preview/ProfileFields.tsx) | [프로필 완료 조건](../specs/profile.md#acceptance-criteria): 학적·학년 선택, 이름/소개/경험/제목 길이·관심/역할 개수, 기타 제거, 주당 합산 시간 4구간 단일 선택, 전체 공개 전환 확인·기존 지원자 최신 프로필 검토, 선택형 마스코트 |
| 본인 공개 화면 확인 `/profile/public` | [AccountPages](../../design-reference/src/features/design-preview/AccountPages.tsx) | [사람 탐색과 공개 설정](../specs/profile.md#people-directory): 본인이 설정한 공개 결과 확인 |
| 사람 탐색·상세 `/explore?tab=people`, `/people/:personId` | [ExplorePages](../../design-reference/src/features/design-preview/ExplorePages.tsx) | [사람 탐색 공개 정책](../specs/profile.md#acceptance-criteria): `함께할 사람`에서 로그인 후 공개 프로필 검색·번호 페이지·전체 등록 항목 열람. 비공개 프로필의 일반 검색·AI 결과·직접 상세 접근 제외. 지원자 관계와 구분 |
| AI `/ai` | [AiChatPage](../../design-reference/src/features/design-preview/AiChatPage.tsx) | [LLM 추천 완료 조건](../specs/matching.md#acceptance-criteria): 로그인 후 메시지 최대 1,000자·답변 카드 합계 최대 3개·추가 요청·중단·실패·재시도·빈 결과. 기존 지원자 최신 검토와 일반 사람 추천 권한 구분. 실제 LLM은 미구현 |
| 상단 알림함 · 별도 경로 없음 | [Notifications](../../design-reference/src/features/design-preview/Notifications.tsx) | [알림 완료 조건](../specs/notifications.md): 업무 변경별 생성·중복 방지·이전 이력·읽음·모두 읽음·수신자 관계·관련 화면 이동·뒤로 가기로 닫기. 마감 알림 제외 |
| 시작·없는 경로 `/loading`, 정의되지 않은 주소 | [LoadingPage](../../design-reference/src/features/design-preview/LoadingPage.tsx), [라우트](../../design-reference/src/pages/DesignPreviewPage.tsx) | 시작 안내와 찾을 수 없는 대상·경로에서 탐색으로 돌아가기 |

UI에서 확인할 수 있는 흐름과 명세 전체의 구현 완료는 다릅니다. 특히 API 오류·서버 권한·동시 선발·영구 저장은 레퍼런스의 로컬 상태만으로 검증되지 않습니다.

## 확인할 상태와 연결

| 흐름 | 화면을 검토할 때 함께 확인할 것 |
| --- | --- |
| 탐색 → 상세 → 복귀 | 검색·선택한 탭·필터·정렬·페이지를 URL에 유지. 레퍼런스는 각 페이지 6개, 제품은 공모전 12개·팀/사람 6개. 처음 버튼과 최대 5개 번호를 한 줄로 표시. 조건 변경 시 1페이지, 잘못된 페이지·결과 감소 보정. 페이지 이동 시 결과 제목으로 포커스/스크롤 이동. 레퍼런스는 메모리에서 조회하며, 제품의 조회·집계는 [API 페이지 계약](../api/conventions.md#pagination)을 따름. 이전 스크롤 위치 복원은 별도 |
| 탐색 필터·정렬·초기화 | 필터 아이콘 → Drawer의 분야/역할 초안 선택 → 적용 시 URL 반영. 취소·Escape·바깥 닫기 시 미적용 선택 제거, 다시 열면 적용값 복원. 팀의 모집중만 조건, 정렬만 변경했을 때도 초기화 아이콘 표시·기본 조건 복원 |
| 탐색 → AI | 공모전·팀·사람 세 탭 모두 검색창 오른쪽 안의 AI 아이콘으로 이동. 비로그인은 로그인 안내 후 이어가기. AI 진입과 검색어 지우기는 각각 독립된 44px 조작 영역·접근성 이름 제공 |
| 워크스페이스 → 내 지원·팀 만들기 | 내 팀·내 지원 콘텐츠 제목과 개수 옆에 작업 아이콘 배치. 목록 아이콘의 접근성 이름·title은 `내 지원`, 더하기 아이콘은 `팀 만들기`. 각각 44px 조작 영역을 유지하고 팀 만들기는 녹색 주요 행동으로 표시. 내 지원 화면에서는 해당 아이콘의 `aria-current`·녹색 선택 상태와 `내 팀으로` 복귀 링크 확인 |
| 워크스페이스 → 팀 공간 | 모집 중은 녹색 배경, 모집 마감·정원 마감은 회색 배경의 상태 배지로 구분하고 상태 문구도 함께 유지. 카드 전체가 링크이며 접근성 이름은 팀 이름과 `팀 공간으로`를 포함. 카드 안 이동 문구는 생략하고 내 역할·확정 인원 요약과 같은 행의 우하단 화살표로 이동 가능성을 표시. 공개 모집글과 선발 이후의 명시적 `팀 공간으로` 버튼은 유지 |
| 팀 만들기 → 공모전 선택 | Drawer 열기·검색·선택·취소·닫기, 결과가 많을 때 추가 표시, 팀장 포함 총인원 안내와 공식 인원 범위 오류 |
| 프로필 수정 → 저장 | 첫 기본 정보 카드 상단에 수정 아이콘·공개 상태 스위치·미리보기 아이콘을 묶어 배치. 좁은 화면에서는 이 묶음을 다음 줄로 배치하며 세 조작은 나란히 유지. 수정 아이콘으로 편집 진입. 접근성 이름·title은 `프로필 수정`, 조작 영역은 44px이며 수정 화면 제목은 유지. 캐릭터 팝업 선택·취소·프로필 저장, 기본 스콘, 공개 결과·팀 공간에서 같은 이미지 표시, 학사 상위 선택 변경, 경험 미입력/경험 없음 구분, 기본 비공개, URL 수정·삭제가 전체 공개 상태를 바꾸지 않는지 확인, 취소 시 미저장 값 제거 |
| 프로필 공개 → 미리보기 | 상단 `공개`/`비공개` 스위치의 접근성 이름은 `프로필 공개`. 양방향 전환에서 검색·전체 항목 노출과 지원 팀장 예외를 설명하는 Drawer를 열고 `공개로 전환`/`비공개로 전환` 확인 후 저장. 취소·Escape·바깥 닫기는 기존 상태 유지. 눈 아이콘의 `공개된 모습 보기`는 `/profile/public`으로 이동하며 비공개 상태도 그대로 보여줌 |
| 프로필 이미지 선택 | 큰 장식 제목을 두지 않고 `마음에 드는 파워프렌즈를 골라보세요.`를 작은 설명으로 표시. `프로필 이미지 변경` Drawer 제목은 `sr-only`로 유지하며 선택·적용·취소와 포커스 복귀 확인 |
| 학교 인증 안내 | 내 프로필의 빨간 `교내 미인증` 배지를 누르면 미제공 기능 안내 Drawer 표시. 확인·Escape·바깥 영역 닫기와 배지 포커스 복귀 제공. 파란 `교내 인증` 배지 스타일은 후속 인증 상태용으로 준비하며 현재 계정에 인증을 부여하지 않음 |
| 지원 → 내 지원 | 로그인·공개 필수·필수 프로필 점검. 비공개는 공개 범위 팝업 확인·저장 후 조건 재확인, 자동 지원 없음. 학적/학년은 선택, 자격 정보 부족은 원문 확인 안내 후 일반 접수. 선택 메시지 1,000자와 중복·마감·정원·소속 제한 유지 |
| 팀장 검토 → 선발 | 해당 팀장 권한, 비공개라도 등록한 전체 현재 프로필 표시, 최신 프로필 기반 AI 검토와 지원 메시지의 본인·지원 팀장 제한, 일반 팀원의 비공개 접근 제한, 선발 즉시 멤버 반영·남은 자리 감소, 마지막 자리·공모전별 소속 제한 |
| 선발 후 취소 → 재지원 | 팀 공간 접근 종료·자리 반환, 과거 선발 복원 없이 새 지원, 현재 모집 종료·정원 조건 재확인 |
| AI → 추천 카드 → 상세 | 로그인 후에만 대화·입력·결과 제공. 비로그인 직접 주소·로그아웃 뒤에는 로그인 안내이며 이전 대화·입력 제거. 준비 중·중단·오류·재시도·결과 없음, 공개 정보 제한, 다시 돌아왔을 때 대화 유지. 이전 카드 표시·복사에도 현재 공개 범위·모집 상태·마감·정원 반영, 입력창과 하단 영역의 겹침 |
| AI → 새 대화 | 입력창 왼쪽 도구 아이콘으로 시작. 접근성 이름·title은 `새 대화`, `type="button"`으로 전송과 분리하며 대화·입력 초안 초기화 동작 유지. 과거 대화 목록·검색·다시 열기 없음 |
| 알림 → 관련 화면 | 지원 상태 변경/신규 지원 두 계열. 성공한 업무 변경에서 수신자별 한 번 생성, 재시도 중복 없음, 다음 변경은 새 미읽음으로 추가·이전 읽음 유지. 열기만으로 읽음 처리하지 않음. 뒤로 가기·닫기는 알림함만 닫기, 항목 클릭은 최신 권한 재확인. 실패 시 읽음·개수 유지 후 재시도 |

반응형 확인은 320px·390px·430px 모바일 폭을 기준으로 합니다. 팝업 포커스·닫기·키보드, 긴 제목·설명, 큰 글꼴, 안전 영역과 세로 스크롤을 함께 검토합니다. 테스트 결과·스크린샷은 검증한 커밋과 함께 PR에 연결합니다.

공개 사람 상세·본인 공개 미리보기·지원자 상세의 등록 항목은 [ProfileDetails](../../design-reference/src/features/design-preview/ProfileDetails.tsx)를 함께 참고합니다. 학사 정보·관심·역량·경험·자기소개·주당 참여 가능 시간·포트폴리오 URL/제목을 같은 정보 계층으로 표시합니다. 인증 정보나 미수집 연락처를 공개 항목으로 추가하지 않습니다. 기존 지원을 받은 팀장은 비공개 전환 후에도 전체 현재 프로필을 직접 보고 해당 지원의 AI 검토에 최신 정보를 반영할 수 있습니다. 일반 검색·AI 사람 추천에는 제외하며 지원서·요약·과거 공개 정보로 우회 노출하지 않습니다. 제품의 모델 입력 최소화와 현재 권한 검사는 [AI API](../api/ai.md), 대화 저장의 현재 범위와 남은 보존·삭제 결정은 [AI 저장](../database/ai.md)을 따릅니다.

프로필의 주당 시간은 모든 참여 프로젝트 합산 참고값이며 네 구간(`5시간 미만`, `5~10시간 미만`, `10~20시간 미만`, `20시간 이상`) 중 단일 선택입니다. 미입력은 최저 구간과 구분하며 팀별 약속·잔여 시간이 아닙니다. 학적·학년은 선택, 관심 1~3개·역할 1~2개, 이름 50자·소개 300자·경험 500자·포트폴리오 제목 50자를 검증하고 초과 입력을 보존합니다. 기타와 보충 입력은 제거합니다. 학사 종속값은 같은 관계의 유효값을 유지하고 다른 소속 관계의 값만 초안에서 비우며 취소하면 이전 저장값을 유지합니다. 실제 학사 식별자·관계 전수 검증은 별도입니다.

공모전 탐색 카드는 왼쪽 40%를 세로 포스터 영역으로 사용하고 이미지 아래에 별도 문구를 두지 않습니다. 원본 이미지를 자르지 않으며 제목이 길어지면 카드 높이를 늘립니다. 오른쪽은 제목·분야·주최자 순으로 배치하고 우하단의 팀 아이콘·숫자로 모집 상태와 관계없이 공모전에 연결된 모든 팀 수를 표시합니다. 접근성 이름에는 `연결된 팀 N개`를 포함합니다. 별도 상세보기 문구·화살표, 참가 대상·접수 마감 정보 행은 두지 않습니다. D-day는 포스터 위에 유지하고 정확한 마감일·참가 대상은 상세에서 확인합니다. 카드 전체의 클릭·키보드 이동과 녹색 hover·포커스·누름 상태를 유지합니다.

키·값 정보는 공모전 상세, 팀 목록·공간, 내 프로필·공개 프로필·지원자 검토에서 같은 [정보 계층](tokens.md)을 사용합니다. 워크스페이스 팀 카드는 내 역할과 확정 인원/정원으로 요약하고, 중복되는 `팀장 포함 총 N명` 안내는 생략합니다. 요약 옆 화살표는 별도 버튼이 아니며 카드 링크의 일부입니다. 팀 만들기·모집 상세의 정원 안내와 팀장 포함 정원 계산 정책은 유지합니다.

<a id="remaining-decisions"></a>

## 남은 정책과 구현 결정

레퍼런스의 모의 구현과 현재 제품의 미구현 범위를 구분합니다. 이미 확정·구현된 계약은 아래 원본을 따르며, 남은 운영·제품 정책을 임의로 정하지 않습니다.

| 영역 | 확정·구현된 범위와 남은 작업 | 원본 |
| --- | --- | --- |
| AI 모델·도구·실행·검증·저장 | Luna 기반 서버·입력 최소화·현재 권한 검사·실행 메타데이터·일반 채팅 저장은 구현. 실제 화면 연결·품질/비용 평가·원문 보존/삭제의 운영 결정은 후속 | [AI 구조](../development/ai-architecture.md), [MATCH-10·12·13](../specs/matching.md#open-questions) |
| 공고 조건 변경 | 원문 안내와 현재 공고 기한·인원 검사는 구현. 주최 측 변경의 기존 지원·선발·소속 영향은 미정 | [MATCH-08](../specs/matching.md#open-questions), [TEAM-06](../specs/team-recruitment.md#open-questions) |
| 프로필과 탈퇴 | 팀 생성의 이름·관심·역할 요건과 공개 불필요 조건은 확정. 탈퇴·보존·복구 및 추가 개인화 범위는 후속 | [PROFILE-03·04](../specs/profile.md#open-questions) |
| 팀·지원 편집 | 상태 전이·재지원·소속·공고 마감 전 선발 기준은 확정. 모집글/지원 메시지 편집 범위·추가 팀 공간 기능은 후속. 팀장 선발 취소·강퇴·탈퇴·팀 삭제는 MVP 제외 | [팀 미정 사항](../specs/team-recruitment.md#open-questions), [MVP 제외](../specs/team-recruitment.md#membership-exclusions) |
| 공고 운영 | 검증된 JSON 신규 입력 CLI와 공개 탐색은 구현. 최종 수집/검수 도구·관리자 화면·공고 요약·공개 후 변경 운영은 후속 | [공고 미정 사항](../specs/contests.md#open-questions) |
| 학사·선택지 | 선택지 저장 코드와 문서 기반 개발 학사 ID·관계는 구현. 현행 학년도 공식 원장 대조와 운영 이관은 후속 | [학사 명세](../specs/academic-structure.md), [선택지 미정 사항](../specs/profile-options.md#open-questions) |
| 인증 | 세션·쿠키·CSRF·시도 제한·차단 목록 파일 검증은 구현. 실제 키·목록·HTTPS 배포와 운영 정리는 후속이며 계정 복구는 MVP 제외 | [인증 명세](../specs/authentication.md#open-questions) |
| 알림 | 사건·수신자 고유성·상태 변경과 원자적 저장·읽음 API 및 화면은 구현. 장기 보존·추가 전달 방식은 후속 | [알림 명세](../specs/notifications.md) |

팀장이 선발하면 즉시 팀원 확정, 팀장 포함 총 정원, 선발 시 자리 차감, 취소 후 자리 반환·현재 조건에 따른 즉시 재지원은 이미 정해진 정책입니다. 학적·학년 선택, 정보 부족 시 원문 안내 후 일반 지원, 신규 지원 공개 필수, 모집 마감/정원 충족 후 기존 지원자 AI 검토도 확정됐습니다. 같은 공모전의 다른 팀에 동시 지원할 수 있고 선발되면 다른 대기 지원은 폐기됩니다. 새 선발 후보는 유효한 지원 완료·검토 중만 포함합니다. 정원 충족으로 모집이 닫힌 후 자리 반환만으로 다시 열리지 않으며 팀장이 직접 재개합니다. 개별 참가 자격은 지원·선발의 자동 차단 조건이 아닙니다. 이를 별도 수락/자격 확인 대기나 새 TBD로 되돌리지 않습니다.

2026-10-21에는 [팀 모집 두 상태·지원별 검토 시작·미선발](../specs/team-recruitment.md#team-state-transitions), [마감 종류별 선발 가능 시점](../specs/team-recruitment.md#selection-window), [재지원·소속 경계](../specs/team-recruitment.md#reapplication)와 팀 생성에 따른 대기 지원 폐기를 추가로 확정했습니다. 이번 PR은 명세·DB·API 설계 반영이며 아래 참고 화면에 새 정책이 구현·검증됐다는 뜻은 아닙니다. 적용 차이는 [디자인 대조 기록](../specs/prototype-alignment.md#policy-follow-up)에서 관리합니다.

## 재현 경로

- `/explore?q=로컬`: 이미지가 없는 공모전의 스콘 기본 커버. 공모전 선택창과 AI 공모전 추천에도 같은 fallback을 적용하며 이미지 로드 실패도 처리.
- `/explore?sort=deadline`: 마감 임박순만 적용된 상태에서 초기화 아이콘 확인. 필터 Drawer에서 분야 선택·취소·적용·다시 열기 확인.
- `/contests/archive`: 마감 공고 읽기 전용 상세·원문 링크.
- `/ai?scenario=error`: 첫 응답 실패 후 같은 요청 재시도. `마케팅 역할 사람 찾아줘`로 결과 없음 확인.
- `/explore?scenario=notification-error`: 로그인한 상태에서 첫 읽음 처리 실패·재시도.
- `/teams/greenwave?view=applicants`: 팀장 검토·선발·확정 팀원.
- `/workspace?view=applications`: 기존 선발된 로컬 크루 지원 취소·접근 종료 확인.
- `/teams/greenwave?view=space&scenario=team-lifecycle`: 새로 로드한 뒤 로그인하면 마감·여석 상태에서 다시 모집하기 → 확인 → 성공을 확인. 취소·닫기는 상태 유지.
- `/teams/greenwave?view=applicants&scenario=team-lifecycle`: 폐기 상태·사유, 검토 대기 수에서 제외, 팀장의 재개 행동.
- `/applicants/app-seoyeon?scenario=team-lifecycle`: 폐기된 지원의 전체 프로필·기존 지원서 AI 검토와 재요청 유지, 선발·새 AI 후보 추천 제외.
- `/workspace?view=applications&scenario=team-lifecycle`: 로컬 스튜디오 폐기 이력·사유, 로컬 크루 선발 후 본인 지원 취소 시에도 폐기 이력 유지.
- `/reference/notices/campus`, `/reference/portfolios/seoyeon`: 실제 기관·개인 사이트를 대신하는 로컬 링크 목적지.

모든 경로에 `/design-preview` 접두사를 붙입니다. `scenario=team-lifecycle`은 페이지를 새로 로드할 때만 예시 상태를 구성하며 로그인 권한을 우회하지 않습니다. 이후 내부 화면 이동 중에는 같은 상태를 유지하고, 기본 예시로 돌아가려면 쿼리 없는 주소로 새로 로드합니다. 현재 시각은 재현을 위해 2026-10-18로 고정한 예시이며 실제 운영 시계가 아닙니다. 마감 계산은 원문 시각·시간대를 우선하고, 누락 시 한국시간·해당 날짜 종료(다음 날 00:00)를 사용합니다. 상세의 날짜·정보 확인일·원문 링크는 유지하며 시각·시간대 보완 설명 문단은 표시하지 않습니다. 기존 지원자의 AI 검토 결과 확인·재요청은 마감/정원 충족 후에도 허용하고 신규 지원·정원 초과 선발 제한과 구분합니다. 마감 후 실제 추가 선발 허용 범위는 [2026-10-21 확정 정책](../specs/team-recruitment.md#selection-window)을 따르며 참고 화면 반영은 후속 작업입니다.

## 페이지 이동과 공모전별 팀 목록

탐색의 세 탭은 [ListPagination](../../design-reference/src/features/design-preview/ListPagination.tsx)과 [useListPage](../../design-reference/src/features/design-preview/use-list-page.ts)를 함께 사용합니다. `page`로 번호를 유지하며 총결과 수는 현재 조건과 열람 범위를 적용한 수입니다. 비로그인의 사람 탭에는 결과 수·페이지 조작을 노출하지 않습니다. 검색·필터 적용·정렬·탭·초기화는 1페이지로 돌아갑니다. 0건이면 페이지 조작을 숨기고, 1페이지뿐이면 비활성 처음 버튼과 현재 번호를 표시합니다. 처음 버튼을 맨 왼쪽에 두고 현재 페이지를 중심으로 최대 5개의 연속 번호를 한 줄에 배치합니다(최대 6개 조작). 번호를 선택하면 표시 범위도 이동하며 양 끝에서는 범위를 보정합니다. 이전·다음·마지막 버튼은 제공하지 않습니다. 제품 API·DB의 페이징/집계는 [API 계약](../api/conventions.md#pagination)과 [실제 통합 검증](../development/bug-bash.md)에서 확인합니다.

공모전 상세의 `함께할 팀`에는 현재 공모전과 연결된 공개 팀을 직접 표시합니다. [TeamCard](../../design-reference/src/features/design-preview/TeamCard.tsx)를 탐색과 공유하고, 상세 안에서는 중복 공모전명을 생략합니다. 팀이 6개를 넘으면 `teamPage`로 페이지를 나누고 팀 모집글에서 복귀할 때 원래 공모전·팀 페이지·탐색 복귀 경로를 유지합니다. 모집 중 표시는 모집 중/지원자 검토 상태이면서 공고·팀 모집 기한 안에 있고 잔여 정원이 있는 경우로 판단합니다. 이 판정은 탐색 필터와 카드 상태에 공통 적용하며 개인 참가 자격 충족을 뜻하지 않습니다. 공모전 카드의 연결 팀 수는 이 모집 판정으로 줄이지 않습니다.

팀 찾기 버튼을 없애고 팀 영역 오른쪽에 AI·생성(+) 아이콘을 둡니다. 생성은 현재 공모전을 미리 선택하며, AI는 로그인 전용 대화로 이동합니다. 공모전 조건을 자동 전송하지 않습니다. 접수 중인 공고에 팀이 없으면 첫 팀 생성을 권합니다. 공식 인원이 1명이면 정원 1명의 팀으로 생성하며 준비 모임 예외를 제공하지 않습니다. 접수 예정/마감 공고는 기존 팀·공고를 열람하고 생성·AI 아이콘을 숨깁니다. 접수 예정은 시작 후 생성을 안내하고 마감은 생성 권유를 표시하지 않습니다.
