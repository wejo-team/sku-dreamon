# 로고·마스코트 이미지 출처

2026-10-18에 확인한 공식 원본과 프로젝트에서의 용도를 기록합니다. 화면에서 외부 이미지 주소를 직접 호출하지 않고 `design-reference/public/`에 보관한 파일을 사용합니다. 색상 적용 기준은 [스타일과 컴포넌트](tokens.md)를 함께 확인합니다.

## 서비스 로고

- 파일: `design-reference/public/brand/dreamon-logo.png`
- 원본: 팀이 디자인 변경 요청에 첨부한 `codex-clipboard-d7f734c5-11d5-4d20-ad68-ec9da9f35e1d.png`.
- 사용: 상단 브랜드와 서비스 진입 화면의 서경드림온 로고. 첨부 원본을 보존하며, 표시 크기와 배치는 CSS에서 조절합니다.

## 프로필 선택 이미지

[서경대학교 대학마스코트 페이지](https://www.skuniv.ac.kr/mascot)의 파워프렌즈 캐릭터 아이콘 원본입니다. 투명 PNG를 변형 없이 저장했으며, 원형 또는 둥근 배경과 이미지 여백은 화면 컴포넌트에서 처리합니다.

| 캐릭터 | 저장 파일 | 원본 크기 | 공식 이미지 |
| --- | --- | --- | --- |
| 스콘 SKON | `design-reference/public/mascots/skon.png` | 200 × 199 | [skon-head.png](https://www.skuniv.ac.kr/wp-content/themes/_tw/theme/assets/images/mascot/skon-head.png) |
| 아티 ARTI | `design-reference/public/mascots/arti.png` | 200 × 214 | [arti-head.png](https://www.skuniv.ac.kr/wp-content/themes/_tw/theme/assets/images/mascot/arti-head.png) |
| 디모 D-MO | `design-reference/public/mascots/dmo.png` | 200 × 222 | [d-mo-head.png](https://www.skuniv.ac.kr/wp-content/themes/_tw/theme/assets/images/mascot/d-mo-head.png) |
| 비아트 B-ART | `design-reference/public/mascots/bart.png` | 200 × 195 | [b-art-head.png](https://www.skuniv.ac.kr/wp-content/themes/_tw/theme/assets/images/mascot/b-art-head.png) |
| 컨버 CONVER | `design-reference/public/mascots/conver.png` | 200 × 149 | [conver-head.png](https://www.skuniv.ac.kr/wp-content/themes/_tw/theme/assets/images/mascot/conver-head.png) |

이미지와 캐릭터의 원 출처는 서경대학교입니다. 공식 페이지는 2017년 이모티콘 16종에 대해 비상업적·개인적 이용 조건을 별도로 안내합니다. 위 표의 캐릭터 아이콘은 해당 이모티콘 파일이 아니며, 이 문서는 공개 라이선스나 포괄적인 재배포 허가를 새로 부여하지 않습니다.

## 공모전 기본 이미지

- 용도: 공모전 이미지가 없거나 불러오지 못했을 때 사용하는 공통 이미지.
- 저장 파일: `design-reference/public/contest-covers/skon-default.png`.
- 캐릭터 참고 원본: 공식 소개의 [스콘 전신 이미지](https://www.skuniv.ac.kr/wp-content/themes/_tw/theme/assets/images/mascot/skon.png).
- 생성: 2026-10-18, Codex 내장 ImageGen. 공식 스콘 전신 PNG를 이미지 참고로 제공해 생성한 파생 일러스트이며 공식 공모전 포스터가 아닙니다. 1254 × 1254 PNG 결과를 원본 그대로 보관합니다.
- 프롬프트 요약: 스콘의 아이보리 호랑이 형태·녹색 전원 기호 얼굴·가슴 잎사귀·전선 꼬리를 유지하고, 작은 무지 포트폴리오를 든 중앙 구도. 옅은 세이지 배경, 부드러운 3D 질감과 접지 그림자, 작은 썸네일에서 알아볼 수 있는 얼굴, 글자·워터마크·추가 캐릭터 없음.
- 적용: [ContestCover](../../design-reference/src/features/design-preview/ContestCover.tsx)가 빈 이미지와 로드 실패에 같은 기본값을 사용합니다. 탐색 카드, 공모전 선택 팝업, AI 공모전 추천 카드가 공유합니다. `local` 공모전은 이미지 없는 예시이며 다른 공모전의 기존 커버는 유지합니다.

## 홈페이지에서 참고한 색상

[서경대학교 메인 홈페이지](https://www.skuniv.ac.kr/main)의 실제 CSS와 브라우저 계산값을 확인했습니다. 기본 주소는 입학 안내 인트로로 이동하므로 메인 경로를 기준으로 합니다. 원본은 [공식 테마 CSS](https://www.skuniv.ac.kr/wp-content/themes/_tw/theme/style.css?ver=1791945423)이며, 아래 값은 조회 시점의 웹사이트 스타일이지 별도 공식 브랜드 가이드로 간주하지 않습니다.

| 원본 토큰·선택자 | 확인한 색상 | 원본에서의 역할 |
| --- | --- | --- |
| `--wp--preset--color--primary`, `.button.primary` | `#007A55` | 기본 강조색, 주요 버튼 |
| `--color-point`, `.button.primary:hover` | `#15803D` | 버튼의 포인터 상태 등 강조 |
| `--color-primary-50`, `--color-primary-100` | `#F2FBF6`, `#D0E9DD` | 녹색 계열의 옅은 배경 토큰 |
| `--color-primary-800` | `#00573A` | 진한 녹색 토큰 |
| `--wp--preset--color--secondary` | `#453587` | 보조 보라색 |
| `--wp--preset--color--tertiary` | `#0369A1` | 보조 파란색 |
| `--wp--preset--color--text-primary` | `#101828` | 기본 글자색 |
| `--color-bg-primary` | `#FFFFFF` | 기본 표면 |
| `.today-section`, `.global-footer`의 `--color-primary` 재정의 | `#20D735` | 어두운 영역 위의 밝은 포인트 |

메인 화면의 공지 영역은 흰 바탕과 옅은 회색 카드, 녹색 선택 표시를 조합합니다. 레퍼런스에서는 이 역할 구분을 참고하되 모바일 카드와 배경의 대비 및 작은 글자 가독성에 맞춰 조정합니다. 밝은 포인트 색을 흰 바탕의 본문 글자나 주요 버튼 글자에 그대로 사용하지 않습니다.
