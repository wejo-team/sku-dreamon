# 문서 관리와 게시

## 원본과 편집

- 사람과 에이전트에게 전달하는 작업 지침·명세·개발 정보는 `docs/`에서 관리합니다. 루트 `AGENTS.md`는 문서 인덱스로 들어오는 링크만 유지합니다.
- `docs/README.md`와 하위 폴더의 `README.md`는 짧은 인덱스입니다. 문서의 목적과 언제 읽을지를 안내하고 본문 내용을 반복하지 않습니다.
- 새 문서를 만들면 관련 인덱스에 연결합니다. 작업에 필요한 문서만 읽을 수 있도록 한 문서에 모든 영역의 규칙을 합치지 않습니다.
- [VitePress 문서 사이트](https://wejo-team.github.io/wejo-app/)를 기본 읽기 화면으로 사용하고, [GitHub Wiki](https://github.com/wejo-team/wejo-app/wiki)에도 같은 원본을 게시합니다. 두 게시본 모두 수정은 저장소 PR로 제안합니다. Wiki를 직접 고치면 다음 게시에서 덮어쓸 수 있습니다.
- PR 템플릿은 변경·검증 정보를 수집하는 양식이며, 실제 작업 규칙은 [팀 작업 흐름](workflow.md)을 참조합니다.

## 문서 사이트

- VitePress 설정과 테마는 `docs/.vitepress/`, 문서 도구의 의존성은 루트 `package.json`과 `package-lock.json`에서 관리합니다. 서비스 프론트인 `frontend/`와는 별도로 설치합니다.
- 사이트는 기존 Markdown을 직접 빌드합니다. 별도 문서 사본이나 OpenSpec을 만들지 않습니다. 명세 → 사람 검토 → 개발 계획 → 구현·검증 흐름과 에이전트의 선택적 문서 읽기를 유지합니다.
- 한국어 메뉴, 페이지 목차, 브라우저 내 검색, 다크 모드, 모바일 메뉴를 제공합니다. 검색에 외부 서비스나 AI API를 사용하지 않습니다.
- 화면은 큰 배너 없이 문서 본문을 중심으로 구성하며, 절제된 색상과 실제 파일 경로 표시로 현재 읽는 문서를 쉽게 구분합니다.
- 왼쪽 메뉴는 빌드할 때 `docs/`의 실제 폴더와 Markdown에서 자동 생성합니다. 폴더명을 카테고리로 쓰고, 각 폴더의 `README.md`를 먼저 표시한 뒤 파일명 순서로 정렬합니다. 문서 이름은 첫 번째 `#` 제목을 사용합니다. 숨김 경로와 `public/` 자산 폴더는 메뉴에서 제외합니다.
- 새 문서나 폴더를 추가하면 다음 빌드에서 메뉴에 반영됩니다. 메뉴용 문서 목록을 따로 관리하지 않지만, 사람과 에이전트가 선택해서 읽을 수 있도록 관련 `README.md`에도 목적과 링크를 추가합니다.
- 문서의 마지막 수정 시각은 Git 이력에서, 사이트의 원본 버전은 빌드 대상 커밋에서 가져옵니다. `main` 병합 시 최신 내용을 배포하며 의존성 버전을 자동으로 올리지는 않습니다. 과거 버전별 사이트는 별도 운영하지 않고 Git 이력으로 확인합니다.
- 사이트의 편집 링크는 원본 Markdown으로 연결합니다. 게시된 기능 명세와 실제 구현·배포 완료는 별개이며 명세 상태와 PR을 확인합니다.

## 링크와 게시 형식

- 저장소 내부 링크는 현재 문서 기준 상대 경로로 씁니다. Markdown 페이지, 이미지와 일반 파일을 구분합니다.
- 내부 파일과 일반 Markdown 제목 앵커를 검사합니다. 외부 URL의 접속 가능 여부는 검사하지 않습니다. 로컬 HTML 링크 대신 Markdown 링크를 사용합니다.
- 코드 예시는 fenced code block 안에 둡니다. 설명의 파일명과 명령은 실제 파일·설정에 맞춥니다.
- `README.md` 인덱스는 사이트에서 각 폴더의 `index.html`로 변환합니다. 원본의 상대 `.md` 링크는 유지하고, 빌드 설정이 사이트 URL로 변환합니다. `docs/` 밖의 파일 링크는 GitHub 원본으로 연결합니다.
- `docs/README.md`는 Wiki의 `Home`이 되고, 나머지 페이지는 전체 상대 경로를 이용한 고유 이름을 가집니다. `_Sidebar`와 원본 링크는 자동 생성합니다.
- `.wiki-build/`, `docs/.vitepress/dist/`, `docs/.vitepress/cache/`는 생성 결과이며 커밋하지 않습니다. 문서를 두 위치에서 수동으로 수정하지 않습니다.
- 공개 저장소의 문서 사이트와 Wiki도 공개됩니다. 실제 비밀값·팀원의 개인정보·내부 계정 정보는 문서에 넣지 않습니다.

## 자동화

1. PR에서 `docs-wiki.yml`의 `Validate docs`가 원본 링크·Wiki 변환 테스트와 VitePress 빌드, 생성된 HTML의 내부 링크·앵커·자산을 검사합니다. PR에서는 게시하지 않습니다.
2. 필수 검사와 [팀 작업 흐름](workflow.md)의 병합 기준을 충족해 `main`에 병합되면 같은 검사를 다시 실행하고 Pages 아티팩트를 만듭니다. 코드만 바뀐 경우에도 최신 원본 커밋을 일치시킵니다.
3. `Publish Pages`는 GitHub Pages에 정적 사이트를 배포하고, `Publish Wiki`는 `wejo-app.wiki.git`에 변환 문서를 반영합니다. `main`만 게시하며 이전 커밋의 수동 재실행은 최신 커밋 확인 후 게시를 건너뜁니다.
4. 사이트·Wiki의 원본 커밋 링크로 게시 버전을 확인합니다. 게시 실패는 Actions에서 확인하고 원인 수정 후 최신 `main` 실행을 재시도합니다. Pages와 Wiki의 게시 성공 여부는 각각 확인합니다.

GitHub의 Settings → Pages → Source는 **GitHub Actions**로 설정합니다. 배포 환경 `github-pages`는 `main`만 허용합니다. 문서 변경 PR도 기본적으로 작성자 외 1명의 승인이 필요하며, 프로젝트 리더의 PR 검토 예외는 [팀 작업 흐름](workflow.md)을 따릅니다. 최초 사이트 URL은 첫 배포가 성공한 뒤 사용할 수 있습니다.

공개 저장소·표준 GitHub 호스팅 러너·기본 `github.io` 주소를 사용합니다. 별도 서버·유료 검색·도메인을 구입하지 않으며, Pages 아티팩트는 1일만 보관합니다. 작은 문서 사이트를 무료 저장량 한도 안에서 운영하는 구성입니다. Wiki 최초 페이지는 GitHub UI에서 한 번 생성해야 Git 저장소가 초기화됩니다.

## 로컬 검사

저장소 루트에서 `.nvmrc`의 Node 22.22.1, npm 9.2.0, Python 3.13 이상을 사용합니다.

```bash
npm ci
python3 -m unittest discover -s scripts/tests -v
python3 scripts/export_wiki.py --repository wejo-team/wejo-app --ref HEAD
npm run docs:build
python3 scripts/check_docs_site.py
npm run docs:preview
```

미리보기 주소는 `http://localhost:4173/wejo-app/`입니다. 문서를 수정하며 보려면 `npm run docs:dev`를 실행하고 터미널에 표시된 `/wejo-app/` 주소로 접속합니다. 문서 설정·테마 변경 시 검색, 내부 링크, 좁은 화면의 메뉴도 확인합니다. Wiki 생성 결과는 `.wiki-build/`에서 확인합니다.

VitePress는 안정 버전 1.6.4를 고정합니다. 해당 버전의 Vite·esbuild 개발 서버 의존성에는 알려진 보안 권고가 남아 있습니다. 개발 서버를 외부에 공개하지 않고 로컬에서 사용하며, 운영에는 빌드된 정적 파일만 배포합니다. 의존성 갱신 시 `npm audit` 결과와 공식 지원 범위·빌드·검색·링크 호환성을 함께 검토합니다.

## 저장소 이름을 변경할 때

`docs/.vitepress/`의 GitHub 저장소 주소와 Pages `base`, 이 문서와 인덱스의 사이트 주소, HTML 검사의 기본 `--base`를 함께 변경합니다. 루트 `package.json`의 도구 이름도 맞춥니다. 새 주소에서 자산·하위 문서·검색·편집 링크를 다시 확인합니다.

## 근거

- [VitePress GitHub Pages 배포](https://vitepress.dev/guide/deploy#github-pages)
- [GitHub Pages 사용자 지정 workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Pages 이용 범위](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [GitHub Actions 요금 기준](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
