## 요약
공식 디자인 레퍼런스(`design-reference/`)의 15개 화면을 제품 앱 `frontend/`로 이관하고 실제 라우트에 연결했습니다. 하단 4탭·로고가 더 이상 404로 가지 않고, `docs/design/assets` 스크린샷과 같은 화면을 보여줍니다.

## 관련 이슈
- 선행 PR: #120 (공통 UI·AppShell). 이 브랜치는 #120 브랜치에서 갈라졌으며 **#120의 리뷰 반영 커밋 `fd405ab`(아직 #120 브랜치에 push되지 않음)를 포함**합니다. #120 병합 후 리뷰하면 이 PR의 고유 변경(`f96aea4`)만 남습니다.
- 기준 문서: [docs/design/handoff.md](docs/design/handoff.md), [screens.md](docs/design/screens.md), [tokens.md](docs/design/tokens.md), [docs/development/frontend.md](docs/development/frontend.md), [testing.md](docs/development/testing.md)

## 주요 변경
- **화면**: 탐색(공모전·팀·사람), 공모전/사람 상세, 공개 모집글·팀 공간·지원자 관리·지원자 검토, 팀 만들기, 워크스페이스·내 지원, 내 프로필·공개 미리보기, 로그인·가입, AI, 상단 알림함, 시작·없는 경로
- **구조**(frontend.md 「화면과 상태」): 레퍼런스 단일 폴더를 `features/{explore,workspace,teams,account,ai,notifications,demo}`, `components/common`, `pages/`로 분리. `/design-preview`·`Preview` 접두사 제거(handoff.md: 개발용 식별자)
- **데이터**: 백엔드 API가 없어 레퍼런스와 같은 메모리 상태·예시 데이터(`features/demo`)로 동작. 각 파일에 서버 계약이 아니며 API 연동 시 TanStack Query로 교체한다고 명시(handoff.md 3단계). 새로고침 시 초기화
- **스타일**: 스크린샷과 같은 화면을 위해 레퍼런스 CSS를 `styles/`로 그대로 이관하고, 토큰은 `globals.css` 한 곳으로 병합(tokens.md, frontend.md 「모바일 UI」)
- **UI 컴포넌트**: 레퍼런스의 shadcn/ui 구성 추가(checkbox·label·radio-group·separator·switch·command·input-group·message·bubble·message-scroller, `LICENSE.shadcn`). Drawer는 레퍼런스 클래스로 맞춤. Input/Select 44px 기본 높이와 역할별 반경은 #120 리뷰 결과를 유지
- **의존성**: `@radix-ui/react-{checkbox,label,radio-group,separator,switch}`, `cmdk`, `@shadcn/react` — 레퍼런스와 같은 정확한 버전, npm 9.2.0으로 lockfile 갱신
- **보안 보정**: 접두사 기준이던 `returnTo`/`from` 검사를 앱 내부 경로 기준으로 재작성(외부 주소·`//`·`..` 경로는 기본 화면으로)
- **기타**: health 확인 화면은 `/health`로 이동, `/`는 시작 화면. 기존 `mock-data.ts`·`mock-notifications.ts`는 이관한 예시 데이터로 대체
- **출처 주석**: 모든 이관 파일 상단에 번호순 `[참조 출처]`(레퍼런스 파일·docs·명세 앵커·스크린샷 실제 경로), 코드 영역에 `[출처 N] 요약`

## 변경 전후
- 변경 전: health 화면과 404만 등록. 하단 탭·로고 목적지가 모두 '페이지를 찾을 수 없어요'
- 변경 후: screens.md의 15개 화면 경로가 등록되고 레퍼런스와 같은 로컬 상태 전이(로그인·지원·선발·취소·폐기·재개·알림·AI 모의 응답)가 동작

## 검증
- 실행한 테스트 / 명령 (`frontend/`): `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm test`, `npm run build`
- 확인한 결과:
  - 모두 통과. 테스트 17개 파일·226개 통과(레퍼런스 테스트를 컴포넌트 옆으로 이관, 경로 접두사만 조정하고 검증 동작은 유지)
  - Chromium 390px에서 `docs/design/assets`와 대조: explore, wordmark-login-320, explore-filters, contest-teams, ai-welcome, workspace, profile-view, create-team-320, members — 배치 일치
  - 320px에서 탐색·AI·워크스페이스·프로필·공모전 상세·팀 공간 가로 넘침 없음
- 검증하지 못한 부분과 이유:
  - 430px 화면, `?scenario=team-lifecycle`·`/ai?scenario=error` 등 일부 재현 경로는 브라우저에서 직접 보지 않음(이관한 단위·화면 테스트로만 검증)
  - Playwright, 실기기 키보드·safe-area·홈 인디케이터 미확인
  - 로컬 Node가 v24라 `engine-strict`를 우회해 설치함. Node 22.22.1 환경의 `npm ci`는 CI 결과로 확인 필요

## 리뷰 참고
- `explore-filters-390.png`에는 분야 '기타'가 있지만 #77 결정(기타 제거)에 따라 화면에서는 제외됨 — 스크린샷이 정책 이전 버전
- 빌드 시 번들이 500KB를 넘는다는 경고가 있음. 라우트별 코드 분할은 후속 과제
- 메모리 Provider·예시 타입을 서버 계약으로 승격하지 않아야 함(실제 계약은 `docs/api/`)
- 웹폰트(10.4MB TTF) 최적화는 #120 리뷰에서 정한 대로 후속 작업

🤖 Generated with [Claude Code](https://claude.com/claude-code)
