# 스타일과 컴포넌트

모바일 공식 디자인은 중립 회색 배경과 흰 카드, 에메랄드 주요 버튼을 사용합니다. 서경대학교 홈페이지의 녹색 강조와 밝은 표면을 참고해 본문·조작·상태의 역할을 구분합니다. 기본 카드는 흰 면과 아래쪽 그림자로 구분하고, 선택한 탐색 탭·카드의 hover와 누름·정보의 값에 녹색을 적용합니다. 색상과 수치는 [preview-tokens.css](../../design-reference/src/features/design-preview/preview-tokens.css)가 원본이며 이 문서는 사용 의도를 설명합니다.

## 표면과 상태

| 용도 | 토큰 · 현재 값 | 적용 |
| --- | --- | --- |
| 화면 바탕 | `--surface-canvas: #f1f1f3` | 스크롤 화면의 배경 |
| 콘텐츠 카드 | `--surface-card: #ffffff` | 공모전·팀·사람·AI 결과 카드, 프로필·내용 패널과 지원자 행의 기본 면 |
| 카드 hover·포커스 | `--surface-card-hover: #bdd9c7` | 조작 가능한 카드에 커서·키보드 포커스가 올라온 상태. 녹색 테두리와 함께 표시 |
| 누른 카드 | `--surface-card-pressed: #b2d0bd` | 카드의 누름 상태. 녹색 테두리 유지 |
| 입력·상단·팝업·폼 | `--card`, `--background: #ffffff` | 기본 shadcn 표면과 조작 영역 |
| 카드 안 보조 면 | `--muted: #f2f7f4` | 공모전 카드의 참가 대상·접수 마감 정보 상자 |
| 눌린 면·탭 바탕 | `--surface-sunken: #dfeae3` | 탭 레일·설정·사용자 메시지 등 |
| 본문 | `--foreground: #18352b` | 제목·본문 |
| 주요 행동·선택 | `--primary: #007a55`, hover `#00573a` | 주요 버튼·선택한 탐색 탭·탐색 항목. 선택 탭은 흰 글자·600 두께 |
| 선택한 면 | `--accent: #e1efe7`, 글자 `#00573a` | 선택·hover 영역 |
| AI 보조 강조 | `--ai-soft: #f0edf8`, `--ai-ink: #453587` | AI 시작 아이콘의 보조색 |
| 보조 텍스트 | `--muted-foreground: #52675d` | 흰 조작 면의 설명·부가 정보 |
| 카드 안 보조 텍스트 | `--card-muted-foreground: #40594a` | 카드·내용 패널·지원자 행에서 보조 텍스트 토큰을 덮어씀. hover·누름 상태에서도 대비 유지 |
| 읽기 전용 정보의 값·카드 안 링크 | `--accent-foreground: #00573a` | 날짜·대상·인원·역할 등 값과 상세 보기·팀 공간으로 이동 행동 |
| 경계·입력 | `--border: #d5e2da`, `--input: #71897c` | 카드와 조작 요소의 경계 |
| 포커스 | `--ring: #007a55` | 키보드 포커스 표시 |
| 성공·확정 | `--leaf-soft: #f0fdf4`, `--leaf-ink: #166534` | 성공·완료 상태 |
| 주의·확인 | `--warning-soft: #fffbeb`, `--warning-ink: #92400e` | 확인 필요·주의 상태 |
| 오류·위험 행동 | `--coral-soft: #fef2f2`, `--coral-ink: #b91c1c` | 오류·파괴적 행동 |

루트 [globals.css](../../design-reference/src/styles/globals.css)의 기본값만 가져오면 공식 화면의 표면 대비가 달라집니다. 모바일 범위의 토큰 덮어쓰기와 [service-ui.css](../../design-reference/src/features/design-preview/service-ui.css)의 실제 적용을 함께 확인합니다. 카드 바탕과 화면 바탕을 같은 색으로 합치지 않고, 상태는 색상 외에 문구·아이콘으로도 구분합니다. 주요 버튼·선택 탭의 흰 글자 대비는 5.36:1입니다. 카드 보조 글자는 기본·hover·누름 면에서 각각 7.65:1·5.07:1·4.61:1이며, 정보의 녹색 값은 각각 8.66:1·5.74:1·5.22:1입니다. 흰 조작 면의 기본 보조 글자는 6.07:1입니다. 기본색은 [공식 홈페이지 CSS 확인 기록](assets.md)을 참고합니다.

## 간격·글꼴·입체감

| 항목 | 현재 기준 |
| --- | --- |
| 화면 폭 | `min(100%, 480px)`, 넓은 창에서 가운데 배치 |
| 좌우 여백·섹션 간격 | 20px |
| 모바일 카드 내부 여백 | 16px, 상황별 개별 조정은 실제 CSS 확인 |
| 컨트롤·버튼 반경 | 8px |
| 카드·패널 반경 | 12px |
| 페이지 제목 | 26px, 실제 계층은 화면별 스타일 확인 |
| 읽기 전용 정보의 키 | 13px·500, 보조 텍스트 색상 |
| 읽기 전용 정보의 값 | 16px·600, `--accent-foreground: #00573a`와 숫자 고정 폭 |
| 긴 경험·자기소개 | 16px·400, 줄 높이 1.7 |
| 폰트 | `DreamOn Noto` / Noto Sans KR |
| 주요 조작 영역 | 버튼·아이콘·탭 등에서 최소 44px을 확보 |

카드는 두 겹의 아래쪽 그림자(`--card-shadow`: 3px·12px 오프셋)로 회색 바탕에서 떠 있는 높이를 표현하고 작은 패널은 `--panel-shadow`를 사용합니다. 흰 카드 안에서 공모전의 대상·마감 정보는 옅은 녹색 면으로 구분합니다. 조작 가능한 카드는 hover·키보드 포커스에서 녹색 면과 테두리로 상태를 표시합니다. hover에서는 높이·그림자가 커지고, 누르면 면이 더 짙어지며 그림자가 낮아집니다. 정확한 그림자와 상태별 적용은 토큰·스타일 원본을 참조합니다. 모바일에서 hover에만 중요한 정보나 행동을 숨기지 않습니다. 장식용 그림자보다 표면 대비·여백·제목 계층을 우선하며, 버튼의 강조를 위해 그림자를 반복 추가하지 않습니다.

[information-hierarchy.css](../../design-reference/src/features/design-preview/information-hierarchy.css)는 공모전·팀 정보, 프로필과 지원자 정보의 키·값·설명을 구분합니다. 키는 보조색으로 유지하고 짧은 값은 진한 녹색으로 강조하며, 긴 문단과 빈 상태 안내 전체를 굵게 만들지 않습니다. 긴 설명의 본문 색상은 유지합니다. 상세 정보는 라벨 열과 값 열을 맞추고 긴 값은 줄바꿈하며, 폼 입력 라벨과 실제 섹션 제목은 이 규칙으로 바꾸지 않습니다.

[폰트 파일](../../design-reference/public/fonts/NotoSansKR.ttf)과 [OFL 라이선스](../../design-reference/public/fonts/OFL.txt), 카드의 공모전 커버·로고·파워프렌즈 캐릭터는 레퍼런스의 로컬 자산입니다. 원본 및 생성 이미지의 출처는 [자산 문서](assets.md)를 따릅니다. [PreviewUi](../../design-reference/src/features/design-preview/PreviewUi.tsx)의 사용처를 확인하고 파일·라이선스를 함께 유지합니다. 실제 인물 사진·공고 포스터로 오인해 서비스 데이터의 출처로 사용하지 않습니다.

## shadcn/ui 사용 맵

| 상황 | 참고 컴포넌트·원본 |
| --- | --- |
| 주요/보조 행동·링크 | [Button](../../design-reference/src/components/ui/button.tsx), [PreviewUi](../../design-reference/src/features/design-preview/PreviewUi.tsx) |
| 워크스페이스 작업 | [Button](../../design-reference/src/components/ui/button.tsx)의 링크 조합과 [WorkspacePages](../../design-reference/src/features/design-preview/WorkspacePages.tsx). 내 지원은 `ClipboardList`, 팀 만들기는 `Plus` 아이콘 |
| 입력·선택·설명·오류 | [Input](../../design-reference/src/components/ui/input.tsx), [Textarea](../../design-reference/src/components/ui/textarea.tsx), [NativeSelect](../../design-reference/src/components/ui/native-select.tsx), [Alert](../../design-reference/src/components/ui/alert.tsx) |
| 학교 인증 상태 | [SchoolVerificationBadge](../../design-reference/src/features/design-preview/PreviewUi.tsx). 미인증은 `--school-unverified: #b42318`, 인증은 `--school-verified: #1d4ed8`, 글자는 흰색. 내 프로필의 미인증 배지는 44px 버튼으로 감싸 안내 Drawer를 열고 다른 화면은 상태 배지로 표시. 현재 계정은 모두 미인증 |
| 공개 여부 | [Switch](../../design-reference/src/components/ui/switch.tsx)와 [프로필 설정](../../design-reference/src/features/design-preview/AccountPages.tsx) |
| 다중·단일 선택 | [Checkbox](../../design-reference/src/components/ui/checkbox.tsx), [RadioGroup](../../design-reference/src/components/ui/radio-group.tsx) |
| 프로필 캐릭터 선택 | [Drawer](../../design-reference/src/components/ui/drawer.tsx) + [RadioGroup](../../design-reference/src/components/ui/radio-group.tsx), [AvatarPicker](../../design-reference/src/features/design-preview/AvatarPicker.tsx). 팝업 적용 후 프로필 저장, 취소 시 유지 |
| 공모전 검색 선택 | [Drawer](../../design-reference/src/components/ui/drawer.tsx) + [Command](../../design-reference/src/components/ui/command.tsx), [ContestPicker](../../design-reference/src/features/design-preview/ContestPicker.tsx) |
| 탐색 분야·역할 필터 | [Drawer](../../design-reference/src/components/ui/drawer.tsx) + [RadioGroup](../../design-reference/src/components/ui/radio-group.tsx) + [Checkbox](../../design-reference/src/components/ui/checkbox.tsx), [ExploreFilters](../../design-reference/src/features/design-preview/ExploreFilters.tsx). 초안 선택·취소·적용, 적용한 조건은 URL에 유지 |
| 시간 설정·알림·확인 | [Drawer](../../design-reference/src/components/ui/drawer.tsx), 각 화면의 열기·닫기·취소·적용 흐름 |
| AI 대화·입력 | [Message](../../design-reference/src/components/ui/message.tsx), [Bubble](../../design-reference/src/components/ui/bubble.tsx), [InputGroup](../../design-reference/src/components/ui/input-group.tsx), [MessageScroller](../../design-reference/src/components/ui/message-scroller.tsx) |
| 상태 표시·경계 | [Badge](../../design-reference/src/components/ui/badge.tsx), [Separator](../../design-reference/src/components/ui/separator.tsx) |

컴포넌트는 저장소에 포함된 소스와 고정 의존성을 기준으로 합니다. 공식 사이트의 최신 예제를 복사해 버전·상호작용을 임의로 교체하지 않습니다. 채팅 구성 요소의 출처·라이선스는 [LICENSE.shadcn](../../design-reference/src/components/ui/LICENSE.shadcn)을 유지합니다.

## 모바일 상호작용 확인

하단 탐색은 탐색·AI·워크스페이스·프로필의 네 항목입니다. 상단 우측 알림과 하단 프로필의 역할을 구분합니다. 네 루트 화면의 중복 제목은 `h1.sr-only`로 남기고 시각적인 제목 영역은 두지 않습니다. 공모전·팀·지원자 상세와 프로필 수정 화면의 제목은 유지합니다. AI 화면은 대화·입력창·하단 영역을 함께 배치하며 [PreviewShell](../../design-reference/src/features/design-preview/PreviewShell.tsx)의 `visualViewport` 대응을 확인합니다.

공모전·팀 탐색의 AI 추천 진입 아이콘은 검색창 오른쪽 안에 배치하며 사람 탭에는 표시하지 않습니다. 검색어 지우기와 AI 진입은 각각 독립된 44px 조작 영역으로 유지합니다. 필터와 초기화도 최소 44px 아이콘 버튼으로 표시하며 접근성 이름을 제공합니다. 선택한 필터는 개수와 접근성 설명으로 알리고, 공모전 정렬은 선택 목록을 유지합니다. 정렬만 바꾼 경우에도 초기화 아이콘으로 기본 조건으로 돌아갈 수 있습니다.

워크스페이스는 내 팀·내 지원 콘텐츠 제목, 개수, 작업 아이콘을 한 줄로 배치합니다. 내 지원·팀 만들기 링크는 각각 44px 조작 영역과 행동 이름을 나타내는 `aria-label`·`title`을 제공하고, 팀 만들기는 녹색 주요 버튼으로 강조합니다. 내 지원 화면의 목록 아이콘은 `aria-current`와 녹색으로 현재 위치를 표시합니다. 팀 카드는 전체 링크를 유지하고 내 역할·확정 인원과 같은 행 우하단의 `ChevronRight`로 이동을 나타냅니다. 화살표는 장식으로 처리하며, 카드 링크의 접근성 이름에 팀 이름과 `팀 공간으로`를 포함합니다. 이 카드의 이동 문구만 생략하고 상세·선발 이후의 명시적 이동 버튼은 유지합니다.

내 프로필 보기에서는 첫 기본 정보 카드의 이름·아바타 옆에 `SquarePen` 수정 아이콘을 배치합니다. 44px 조작 영역과 `프로필 수정` 접근성 이름·title을 제공하며 공개/비공개 스위치·눈 모양 미리보기를 같은 조작 묶음에 배치합니다. 반복되는 공개 안내 행과 상시 학교 인증 설명은 표시하지 않습니다. 공개 스위치는 사람 탐색 공개만 즉시 저장하며 별도의 항목별 동의는 보존합니다. AI의 `새 대화`는 입력창 왼쪽 도구 아이콘으로 배치하고 `type="button"`을 사용해 메시지 전송과 구분합니다.

팝업은 열기·닫기·Escape·바깥 영역·포커스 복귀를 확인하고, 폼의 적용과 취소를 구분합니다. 프로필 공개 스위치는 라벨과 설명에서 누구에게 공개되는지 드러내야 합니다. 화면 제목·입력 라벨·오류 메시지·로딩·빈 상태를 유지하고 색만으로 상태를 전달하지 않습니다. 긴 한국어 텍스트·큰 글꼴·화면 확대·작은 높이·키보드가 열린 상태·감소된 모션 설정에서 조작이 가능한지 확인합니다.
