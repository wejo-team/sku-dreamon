# 스타일과 컴포넌트

모바일 공식 디자인은 옅은 세이지 배경과 흰 카드, 에메랄드 주요 버튼을 사용합니다. 서경대학교 홈페이지의 녹색 강조와 밝은 표면을 참고해 본문·조작·상태의 역할을 구분합니다. 밝은 녹색은 마스코트 이미지에 두고, 작은 글자와 주요 행동에는 명암 대비를 확보한 짙은 녹색을 적용합니다. 색상과 수치는 [preview-tokens.css](../../design-reference/src/features/design-preview/preview-tokens.css)가 원본이며 이 문서는 사용 의도를 설명합니다.

## 표면과 상태

| 용도 | 토큰 · 현재 값 | 적용 |
| --- | --- | --- |
| 화면 바탕 | `--surface-canvas: #edf4ef` | 스크롤 화면의 배경 |
| 카드·입력·상단·팝업 | `--card`, `--background: #ffffff` | 바탕과 구분되는 읽기·조작 영역 |
| 카드 안 보조 면 | `--muted: #f2f7f4` | 카드의 보조 정보 |
| 눌린 면·탭 바탕 | `--surface-sunken: #dfeae3` | 탭 레일·설정·사용자 메시지 등 |
| 본문 | `--foreground: #18352b` | 제목·본문 |
| 주요 행동·선택 | `--primary: #007a55`, hover `#00573a` | 주요 버튼·선택한 탭·탐색 항목 |
| 선택한 면 | `--accent: #e1efe7`, 글자 `#00573a` | 선택·hover 영역 |
| AI 보조 강조 | `--ai-soft: #f0edf8`, `--ai-ink: #453587` | AI 시작 아이콘의 보조색 |
| 보조 텍스트 | `--muted-foreground: #52675d` | 설명·부가 정보 |
| 경계·입력 | `--border: #d5e2da`, `--input: #71897c` | 카드와 조작 요소의 경계 |
| 포커스 | `--ring: #007a55` | 키보드 포커스 표시 |
| 성공·확정 | `--leaf-soft: #f0fdf4`, `--leaf-ink: #166534` | 성공·완료 상태 |
| 주의·확인 | `--warning-soft: #fffbeb`, `--warning-ink: #92400e` | 확인 필요·주의 상태 |
| 오류·위험 행동 | `--coral-soft: #fef2f2`, `--coral-ink: #b91c1c` | 오류·파괴적 행동 |

루트 [globals.css](../../design-reference/src/styles/globals.css)의 기본값만 가져오면 공식 화면의 표면 대비가 달라집니다. 모바일 범위의 토큰 덮어쓰기와 [service-ui.css](../../design-reference/src/features/design-preview/service-ui.css)의 실제 적용을 함께 확인합니다. 카드 바탕과 화면 바탕을 같은 색으로 합치지 않고, 상태는 색상 외에 문구·아이콘으로도 구분합니다. 주요 버튼의 흰 글자 대비는 5.36:1, 보조 글자는 흰 카드에서 6.07:1, 눌린 면에서 4.92:1입니다. 기본색은 [공식 홈페이지 CSS 확인 기록](assets.md)을 참고합니다.

## 간격·글꼴·입체감

| 항목 | 현재 기준 |
| --- | --- |
| 화면 폭 | `min(100%, 480px)`, 넓은 창에서 가운데 배치 |
| 좌우 여백·섹션 간격 | 20px |
| 모바일 카드 내부 여백 | 16px, 상황별 개별 조정은 실제 CSS 확인 |
| 컨트롤·버튼 반경 | 8px |
| 카드·패널 반경 | 12px |
| 페이지 제목 | 26px, 실제 계층은 화면별 스타일 확인 |
| 폰트 | `DreamOn Noto` / Noto Sans KR |
| 주요 조작 영역 | 버튼·아이콘·탭 등에서 최소 44px을 확보 |

카드는 `--card-shadow`로 바탕에서 분리하고 작은 패널은 `--panel-shadow`를 사용합니다. 정확한 그림자와 hover 값은 토큰 원본을 참조합니다. 모바일에서 hover에만 중요한 정보나 행동을 숨기지 않습니다. 장식용 그림자보다 표면 대비·여백·제목 계층을 우선하며, 버튼의 강조를 위해 그림자를 반복 추가하지 않습니다.

[폰트 파일](../../design-reference/public/fonts/NotoSansKR.ttf)과 [OFL 라이선스](../../design-reference/public/fonts/OFL.txt), 카드의 공모전 커버·로고·파워프렌즈 캐릭터는 레퍼런스의 로컬 자산입니다. 원본 및 생성 이미지의 출처는 [자산 문서](assets.md)를 따릅니다. [PreviewUi](../../design-reference/src/features/design-preview/PreviewUi.tsx)의 사용처를 확인하고 파일·라이선스를 함께 유지합니다. 실제 인물 사진·공고 포스터로 오인해 서비스 데이터의 출처로 사용하지 않습니다.

## shadcn/ui 사용 맵

| 상황 | 참고 컴포넌트·원본 |
| --- | --- |
| 주요/보조 행동·링크 | [Button](../../design-reference/src/components/ui/button.tsx), [PreviewUi](../../design-reference/src/features/design-preview/PreviewUi.tsx) |
| 입력·선택·설명·오류 | [Input](../../design-reference/src/components/ui/input.tsx), [Textarea](../../design-reference/src/components/ui/textarea.tsx), [NativeSelect](../../design-reference/src/components/ui/native-select.tsx), [Alert](../../design-reference/src/components/ui/alert.tsx) |
| 공개 여부 | [Switch](../../design-reference/src/components/ui/switch.tsx)와 [프로필 설정](../../design-reference/src/features/design-preview/AccountPages.tsx) |
| 다중·단일 선택 | [Checkbox](../../design-reference/src/components/ui/checkbox.tsx), [RadioGroup](../../design-reference/src/components/ui/radio-group.tsx) |
| 프로필 캐릭터 선택 | [Drawer](../../design-reference/src/components/ui/drawer.tsx) + [RadioGroup](../../design-reference/src/components/ui/radio-group.tsx), [AvatarPicker](../../design-reference/src/features/design-preview/AvatarPicker.tsx). 팝업 적용 후 프로필 저장, 취소 시 유지 |
| 공모전 검색 선택 | [Drawer](../../design-reference/src/components/ui/drawer.tsx) + [Command](../../design-reference/src/components/ui/command.tsx), [ContestPicker](../../design-reference/src/features/design-preview/ContestPicker.tsx) |
| 시간 설정·알림·확인 | [Drawer](../../design-reference/src/components/ui/drawer.tsx), 각 화면의 열기·닫기·취소·적용 흐름 |
| AI 대화·입력 | [Message](../../design-reference/src/components/ui/message.tsx), [Bubble](../../design-reference/src/components/ui/bubble.tsx), [InputGroup](../../design-reference/src/components/ui/input-group.tsx), [MessageScroller](../../design-reference/src/components/ui/message-scroller.tsx) |
| 상태 표시·경계 | [Badge](../../design-reference/src/components/ui/badge.tsx), [Separator](../../design-reference/src/components/ui/separator.tsx) |

컴포넌트는 저장소에 포함된 소스와 고정 의존성을 기준으로 합니다. 공식 사이트의 최신 예제를 복사해 버전·상호작용을 임의로 교체하지 않습니다. 채팅 구성 요소의 출처·라이선스는 [LICENSE.shadcn](../../design-reference/src/components/ui/LICENSE.shadcn)을 유지합니다.

## 모바일 상호작용 확인

하단 탐색은 탐색·AI·워크스페이스·프로필의 네 항목입니다. 상단 우측 알림과 하단 프로필의 역할을 구분합니다. AI 화면은 대화·입력창·하단 영역을 함께 배치하며 [PreviewShell](../../design-reference/src/features/design-preview/PreviewShell.tsx)의 `visualViewport` 대응을 확인합니다.

팝업은 열기·닫기·Escape·바깥 영역·포커스 복귀를 확인하고, 폼의 적용과 취소를 구분합니다. 프로필 공개 스위치는 라벨과 설명에서 누구에게 공개되는지 드러내야 합니다. 화면 제목·입력 라벨·오류 메시지·로딩·빈 상태를 유지하고 색만으로 상태를 전달하지 않습니다. 긴 한국어 텍스트·큰 글꼴·화면 확대·작은 높이·키보드가 열린 상태·감소된 모션 설정에서 조작이 가능한지 확인합니다.
