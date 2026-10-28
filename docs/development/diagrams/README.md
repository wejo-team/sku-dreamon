# AI 아키텍처 도표 원본

[AI 에이전트 아키텍처](../ai-architecture.md)에 삽입하는 시각자료입니다. GitHub와 VitePress에서 같은 그림을 읽을 수 있도록 Mermaid 원본과 렌더링한 SVG를 함께 관리합니다. 서비스 코드·설정·운영 배포를 변경하지 않습니다.

| 원본 | 이미지 | 읽는 목적 |
| --- | --- | --- |
| [ai-flow.mmd](ai-flow.mmd) | [처리 흐름](ai-flow.svg) | 입력 가드·단일 ReAct·필수 검증·스트리밍·완료의 순서 |
| [ai-tools.mmd](ai-tools.mmd) | [도구 구성](ai-tools.svg) | 서버 컨텍스트, 도구 팩토리, 목적별 도구, 기존 서비스 연결 |
| [ai-lifecycle.mmd](ai-lifecycle.mmd) | [저장과 전송](ai-lifecycle.svg) | 일반 채팅의 두 저장 트랜잭션과 전송 중 권한 검사 |

## 수정과 재생성

1. 현재 [실행 서비스](../../../backend/app/services/ai.py), [도구](../../../backend/app/agents/tools.py), [실행·저장 제어](../../../backend/app/services/ai_runs.py)를 확인합니다.
2. 해당 `.mmd`를 수정하고 `@mermaid-js/mermaid-cli` **11.12.0**으로 SVG를 다시 생성합니다. 색·폰트·간격은 [공유 설정](mermaid-config.json)에 둡니다.
3. SVG와 문서 사이트를 모두 열어 한국어 글꼴, 겹침·잘림, 화살표 방향, 작은 화면의 확대 경로를 확인합니다. 원본·SVG·관련 설명을 같은 커밋에 포함합니다.

저장소 루트에서 실행합니다. 렌더러는 필요할 때만 실행하며 프로젝트 의존성에는 추가하지 않습니다. 첫 실행에는 CLI와 브라우저 설치를 위한 네트워크가 필요할 수 있습니다.

```bash
python3 docs/development/diagrams/render.py
```

기존 Chromium을 사용할 때는 [생성 스크립트](render.py)의 `--puppeteer-config` 옵션으로 로컬 Puppeteer 설정 파일을 지정할 수 있습니다. 생성 스크립트는 SVG의 고유 너비·높이도 명시해 단독 보기에서 확대·스크롤할 수 있게 합니다. 머신별 실행 파일 경로·임시 설정은 저장소에 넣지 않습니다. 한국어를 지원하는 맑은 고딕 또는 Noto Sans CJK KR을 준비하며, 글꼴이 달라지면 배치도 달라질 수 있습니다. 실제 생성본은 맑은 고딕을 사용했습니다.

문서 빌드는 SVG를 원래 상대 경로에도 복사해 크게 보기 링크를 유지하고, Mermaid·생성 스크립트·설정 링크는 해당 커밋의 GitHub 원본으로 연결합니다.

흰 바탕과 명시적인 글자색으로 라이트·다크 문서 테마에서 같은 대비를 유지합니다. SVG에 접근성 제목·설명을 포함하고 문서에 대체 텍스트와 표·설명을 함께 제공합니다. 긴 그림은 본문의 크게 보기 링크로 원본을 열어 확대할 수 있습니다.
