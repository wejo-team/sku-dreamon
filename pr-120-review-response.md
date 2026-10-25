# PR #120 리뷰 반영 내역

> 이 파일은 리뷰 답변·PR 본문 작성을 위한 초안이며 커밋하지 않습니다. 아래 각 절을 해당 리뷰 코멘트의 답글로 사용합니다.

## 전체 답글 (리뷰 본문에 대한 답)

리뷰 감사합니다. 수정 요청 5건과 권고 3건 중 웹폰트 최적화를 제외한 항목을 반영했습니다. 웹폰트는 권고대로 별도 개선 작업으로 분리합니다.

| 검사 (frontend/) | 결과 |
| --- | --- |
| `npm run lint` | 통과 |
| `npm run format:check` | 통과 |
| `npm run build` | 통과 (`tsc -b` + Vite production build) |
| `npm test` | 4개 파일, 14개 통과 (기존 11개 + 신규 3개) |
| Chromium 화면 확인 | 320·390·430·1280px. 가로 넘침 없음. 네 탭 모두 문구 높이 16px(한 줄)·아이콘 22px 동일 |
| 알림 상호작용 | 키보드로 열기 → 포커스가 알림함 내부로 이동, Tab 6회 모두 내부 유지, Escape 후 벨 버튼으로 복귀. `/workspace` → `/profile` → 열기 → 뒤로 가기 시 `/profile` 유지 + 알림함 닫힘. 항목 클릭 시 관련 화면으로 이동 후 뒤로 가기에서 알림함이 다시 열리지 않음 |

확인하지 못한 범위: 백엔드 연동, 실기기 키보드·홈 인디케이터·화면 회전(safe-area는 CSS와 viewport 설정으로만 확인).

로컬 메모: 이 PC의 Node가 v24라 `engine-strict` 때문에 `npm install`이 거부되어, 의존성 추가는 `npx npm@9.2.0 install vaul@1.1.2 --engine-strict=false`로 실행했습니다. 프로젝트 고정 npm(9.2.0)으로 lockfile을 갱신해 추가분 외 변경이 생기지 않게 했습니다. CI(Node 22.22.1)에서 `npm ci`로 다시 확인합니다.

---

## 1. [P2] Drawer 포커스·접근성 — `frontend/src/components/ui/drawer.tsx`

**변경**: 직접 구현한 div Drawer를 레퍼런스(`design-reference/src/components/ui/drawer.tsx`)와 같은 Vaul 1.1.2 기반으로 교체하고, 프로젝트 스타일(최대 480px 중앙, `rounded-t-2xl`, `bg-card`, `max-h-[85vh]` 스크롤, 핸들 바, 하단 safe-area 여백)만 입혔습니다.

**근거**
- Vaul은 Radix Dialog 위에 만들어져 WAI-ARIA APG Dialog(Modal) 패턴의 요구(열 때 내부로 포커스 이동, Tab/Shift+Tab 순환, Escape 닫기, 닫은 뒤 호출 요소로 포커스 복귀, 배경 inert)를 primitive가 보장합니다.
- `DrawerTitle`/`DrawerDescription`은 Radix가 `aria-labelledby`/`aria-describedby`로 자동 연결하므로 dialog 이름이 비지 않습니다.
- `DrawerTrigger`/`DrawerClose`는 기본 `button`, `asChild`는 Slot 합성으로 실제 동작합니다. 그래서 미사용 `asChild` lint 오류가 함께 사라졌습니다.
- 직접 작성한 Escape·body 스크롤 잠금 `useEffect`는 primitive와 중복되어 제거했습니다.
- 의존성은 `.npmrc`의 `save-exact`에 맞춰 정확한 버전으로 추가했고 lockfile을 함께 갱신했습니다(docs/development/conventions.md).

**검증**: `src/components/ui/drawer.test.tsx` — 키보드로 열기 → dialog 이름 "알림함"·설명 확인 → 포커스가 내부에 있음 → Tab 반복 시 내부 유지, 첫 요소에서 Shift+Tab 시 마지막 요소로 순환 → Escape → 호출 버튼으로 포커스 복귀.

## 2. [P2] 하단 메뉴 safe-area — `AppShell.tsx`, `globals.css`

**변경**: `--bottom-nav-height: calc(4rem + env(safe-area-inset-bottom))` 토큰을 만들었습니다. 메뉴 높이는 이 토큰으로, 아래 패딩은 `env(safe-area-inset-bottom)`으로 확보합니다. 본문 여백은 하단 메뉴가 있을 때 `calc(var(--bottom-nav-height) + 2rem)`로 계산합니다. 기존 `pb-24`(64px + 32px)의 의도는 그대로입니다. 메뉴가 없는 로그인·회원가입 화면은 `pb-8`입니다.

**근거**: `index.html`이 `viewport-fit=cover`이므로 safe-area가 0이 아닌 기기에서는 메뉴가 홈 인디케이터 영역을 피해야 합니다. 높이를 토큰 한 곳에 두어 메뉴와 본문 여백이 같은 값을 쓰게 했습니다. Drawer 시트 하단 패딩에도 같은 safe-area를 반영했습니다.

**검증**: 브라우저(safe-area 0)에서 메뉴 높이 64px 유지를 확인했습니다. 실기기 확인은 하지 못했습니다.

## 3. [P2] 탭 폭 고정 — `AppShell.tsx`

**변경**: 링크의 `size-12`를 `h-12 min-w-0 flex-1`로 바꾸고, 문구에 `whitespace-nowrap`, 아이콘에 `shrink-0`을 적용했습니다. 48px 터치 높이는 유지하고, 탭은 메뉴 폭을 4등분합니다.

**근거**: 폭을 48px로 고정하면 '워크스페이스'가 줄바꿈되고, 늘어난 글자 높이 때문에 아이콘이 줄어듭니다. 공간을 등분하면 4탭 구조를 유지하면서 최소 폭(320px)에서도 76px씩 확보됩니다.

**검증**: 320·390·430·1280px에서 네 탭 모두 문구 높이 16px·아이콘 22px로 같습니다.

## 4. [P2] 알림 날짜 대비 — `features/notifications/NotificationInbox.tsx`

**변경**: `text-muted-foreground/80`을 `text-muted-foreground`로 바꿨습니다.

**근거**: 공통 토큰(`#52675d`)의 대비를 사용처에서 다시 낮추지 않습니다. 합성 배경 기준 대비는 미읽음 카드(accent 40%) 약 5.69:1, 흰 카드 약 6.07:1로 WCAG 1.4.3의 4.5:1을 넘습니다. 날짜의 낮은 중요도는 11px 크기와 하단 배치로 표현합니다.

## 5. [P2] 알림함 뒤로 가기 — `features/notifications/NotificationInbox.tsx`

**변경**: 레퍼런스 `Notifications.tsx`와 같이 열림 상태를 컴포넌트 state가 아닌 history 항목(`location.state.notificationInbox`)에 둡니다.
- 열기: 같은 경로에 state를 담아 push합니다.
- 닫기(Escape·닫기 버튼·배경): `navigate(-1)`로 그 항목만 되돌립니다. 새로고침으로 첫 history 항목에서 열린 경우에는 페이지를 벗어나지 않도록 `replace`로 표시만 지웁니다.
- 브라우저 뒤로 가기: history가 알림 항목을 지우므로 경로는 그대로 두고 알림함만 닫힙니다.
- 항목 클릭: `navigate(item.to, { replace: true })`로 알림 항목을 관련 화면으로 대체해, 이후 뒤로 가기에서 알림함이 다시 열리지 않게 합니다.

**근거**: docs/design/screens.md 알림 행의 "뒤로 가기·닫기는 알림함만 닫기". 알림 상태를 전역 store로 올리지 않았습니다.

**검증**: `src/features/notifications/NotificationInbox.test.tsx` — `/workspace`→`/profile`에서 열기 → 뒤로 → `/profile` 유지 + dialog 닫힘. 닫기 버튼으로 닫아도 경로가 유지되는 것도 확인합니다. 브라우저에서도 같은 흐름을 확인했습니다.

## 6. [권고·구조] 알림 기능 분리

**변경**: 벨 버튼·Drawer·알림 상태(미읽음 수·모두 읽음·항목 읽음)를 `features/notifications/NotificationInbox.tsx` 한 단위로 옮겼습니다. AppShell에는 헤더·본문·하단 메뉴 배치만 남았습니다. 알림 fixture는 `mock-data.ts`에서 `features/notifications/mock-notifications.ts`로 옮기고, 파일 머리 주석에 "화면 확인용 예시이며 계약은 docs/api/notifications.md"라는 경계를 적었습니다. 나머지 mock-data는 권고대로 각 화면을 구현할 때 옮깁니다.

**추가 개선**: 벨 버튼 이름을 레퍼런스와 같은 "알림, 읽지 않은 알림 N개"로 맞췄습니다. 숫자 배지는 `aria-hidden`으로 중복 낭독을 막았습니다. 알림함에 닫기 버튼을 추가했습니다(키보드·스크린리더 사용자가 명시적으로 닫을 수 있는 수단).

## 7. [권고·토큰] hover·반경·그림자 연결 — `globals.css`, `components/ui/*`

**변경**
- Button default의 `hover:bg-primary/90`을 `hover:bg-primary-hover`로 바꿨습니다. 이제 `--primary-hover`가 실제 hover를 제어합니다.
- docs/design/tokens.md의 "컨트롤·버튼 8px / 카드·패널 12px"에 맞춰 역할 토큰 `rounded-control`(8px)과 `rounded-panel`(12px)을 추가했습니다. Button·Input·NativeSelect·Textarea·하단 탭은 `rounded-control`, Alert·알림 카드는 `rounded-panel`을 씁니다. 이전 `rounded-md`(10px)는 기준과 달랐습니다.
- `--card-shadow`/`--panel-shadow`는 `shadow-card`/`shadow-panel` 유틸리티로 매핑만 해 두었습니다. 해당 표면을 구현할 때 사용합니다.
- CSS 파일은 분리하지 않았습니다.

## 8. [권고·성능] 웹폰트 크기 — 후속 작업

이번 PR에서는 반영하지 않았습니다. 후속 작업에서 `NotoSansKR.ttf`(10.4MB)를 WOFF2로 바꾸고, 한글 음절 전체(U+AC00–D7A3)·자모·라틴·문장부호 범위를 유지하는 서브셋 또는 unicode-range 분할을 검토합니다. OFL.txt는 함께 유지합니다.

## 검사 실패 정리 — `App.tsx`

주석 처리된 두 번째 App과 모듈 레벨 JSX 주석을 제거하고, 실제 실행 코드 한 곳만 남겼습니다. 현재 라우트 범위는 주석으로 적었고, Prettier로 포맷을 정리했습니다.

---

## PR 제목·본문 갱신안

**제목**: `feat(frontend): 공통 UI와 모바일 AppShell 추가`

**본문**

### 범위
페이지 개발 전 단계의 공통 UI(Button·Input·NativeSelect·Textarea·Switch·Badge·Alert·Pagination·Drawer), 모바일 AppShell(헤더·알림함·하단 4탭), 디자인 토큰을 추가합니다. 서버 연동과 실제 서비스 페이지는 후속 작업입니다.

### 현재 동작 범위
- 등록된 라우트는 `/`(health 확인)와 404뿐입니다. 하단 네 탭과 로고의 목적지(`/explore`·`/ai`·`/workspace`·`/profile`)는 아직 '페이지를 찾을 수 없어요'로 이동합니다. 각 페이지 작업에서 경로와 활성 탭을 함께 검증합니다.
- AI 화면 키보드 대응은 `--ai-viewport-height`를 설정하기만 합니다. 이 값을 쓰는 높이·스크롤 CSS는 AI 화면을 연결할 때 완성합니다.
- 알림은 화면 확인용 예시 데이터(`features/notifications/mock-notifications.ts`)입니다.

### 검증 (frontend/)
(위 "전체 답글"의 검사 표)

### 후속 과제
- 웹폰트 WOFF2 변환과 한글 범위 서브셋/분할(OFL 유지)
- 페이지 라우트 추가 시 탭·로고 목적지와 활성 탭 검증
- AI 화면 `--ai-viewport-height` 소비와 실기기 키보드 확인
- 실기기 safe-area·홈 인디케이터·회전 확인

🤖 Generated with [Claude Code](https://claude.com/claude-code)
