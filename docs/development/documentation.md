# 문서 관리와 게시

## 원본과 편집

- 사람과 에이전트에게 전달하는 작업 지침·명세·개발 정보는 `docs/`에서 관리합니다. 루트 `AGENTS.md`는 문서 인덱스로 들어오는 링크만 유지합니다.
- `docs/README.md`와 하위 폴더의 `README.md`는 짧은 인덱스입니다. 문서의 목적과 언제 읽을지를 안내하고 본문 내용을 반복하지 않습니다.
- 새 문서를 만들면 관련 인덱스에 연결합니다. 작업에 필요한 문서만 읽을 수 있도록 한 문서에 모든 영역의 규칙을 합치지 않습니다.
- 개발·검토의 기준은 최신 `develop`의 `docs/`입니다. [develop 문서 인덱스](https://github.com/wejo-team/sku-dreamon/blob/develop/docs/README.md) 또는 최신 `origin/develop`에서 시작한 작업 브랜치의 문서를 읽습니다. 기준 커밋과 작업 재개 시 확인 방법은 [팀 작업 흐름](workflow.md)을 따릅니다.
- [VitePress 문서 사이트](https://wejo-team.github.io/sku-dreamon/)는 `main`에 포함된 릴리스 문서를 읽는 화면입니다. `develop`에만 반영된 문서는 저장소에서 확인하며, 수정은 `develop` 대상 PR로 제안합니다.
- PR 템플릿은 변경·검증 정보를 수집하는 양식이며, 실제 작업 규칙은 [팀 작업 흐름](workflow.md)을 참조합니다.

## 문서 이름과 책임

- 폴더는 독자의 직무보다 보관하는 정보의 역할로 구분합니다. `collaboration/`은 문서 협업 방법, `specs/`는 실제 기능 명세, `templates/`는 작성 양식, `development/`는 개발 기준·기술 운영 가이드입니다.
- 파일명은 폴더와 함께 읽었을 때 작업·대상을 알 수 있게 짓습니다. 예를 들어 `collaboration/editing-docs.md`는 문서 편집, `collaboration/review-and-publish-docs.md`는 문서 리뷰와 게시 확인을 안내합니다. 같은 폴더에서 다룰 수 있는 여러 대상 중 무엇을 뜻하는지 모호하면 대상을 이름에 포함합니다.
- 각 폴더 인덱스에 책임과 다른 폴더와의 경계를 적습니다. 작업 방법, 실제 명세, 작성 양식, 공통 규칙은 각각의 원본으로 연결하고 규칙을 중복 정의하지 않습니다.
- 기존 이름을 바꿀 때는 내부 링크뿐 아니라 공개된 사이트 주소와 다른 PR의 참조도 확인합니다. 아직 게시하지 않은 새 문서는 병합 전에 이름을 정리하고, 이미 공유된 문서는 이름 개선의 이점과 이전 주소를 유지할 방법을 함께 검토합니다.

## 문서 사이트

- VitePress 설정과 테마는 `docs/.vitepress/`, 문서 도구의 의존성은 루트 `package.json`과 `package-lock.json`에서 관리합니다. 서비스 프론트인 `frontend/`와는 별도로 설치합니다.
- 사이트는 기존 Markdown을 직접 빌드합니다. 별도 문서 사본이나 OpenSpec을 만들지 않습니다. 명세 → 사람 검토 → 개발 계획 → 구현·검증 흐름과 에이전트의 선택적 문서 읽기를 유지합니다.
- 한국어 메뉴, 페이지 목차, 브라우저 내 검색, 다크 모드, 모바일 메뉴를 제공합니다. 검색에 외부 서비스나 AI API를 사용하지 않습니다.
- 화면은 큰 배너 없이 문서 본문을 중심으로 구성하며, 절제된 색상과 실제 파일 경로 표시로 현재 읽는 문서를 쉽게 구분합니다.
- 왼쪽 메뉴는 빌드할 때 `docs/`의 실제 폴더와 Markdown에서 자동 생성합니다. 폴더명을 카테고리로 쓰고, 각 폴더의 `README.md`를 먼저 표시한 뒤 파일명 순서로 정렬합니다. 문서 이름은 첫 번째 `#` 제목을 사용합니다. 숨김 경로와 `public/` 자산 폴더는 메뉴에서 제외합니다.
- 새 문서나 폴더를 추가하면 다음 빌드에서 메뉴에 반영됩니다. 메뉴용 문서 목록을 따로 관리하지 않지만, 사람과 에이전트가 선택해서 읽을 수 있도록 관련 `README.md`에도 목적과 링크를 추가합니다.
- 문서의 마지막 수정 시각은 Git 이력에서, 사이트의 원본 버전은 빌드 대상 커밋에서 가져옵니다. `main` 릴리스에 포함된 내용을 게시하며 의존성 버전을 자동으로 올리지는 않습니다. 과거 버전별 사이트는 별도 운영하지 않고 Git 이력으로 확인합니다.
- 사이트의 편집 링크는 `develop`의 원본 Markdown으로 연결합니다. 게시된 내용과 편집할 최신 내용은 다를 수 있으므로 변경 전후를 확인합니다. 게시된 기능 명세와 실제 구현·배포 완료는 별개이며 명세 상태와 PR을 확인합니다.

## 링크와 게시 형식

- 저장소 내부 링크는 현재 문서 기준 상대 경로로 씁니다. Markdown 페이지, 이미지와 일반 파일을 구분합니다.
- 내부 파일과 일반 Markdown 제목 앵커를 검사합니다. 외부 URL의 접속 가능 여부는 검사하지 않습니다. 로컬 HTML 링크 대신 Markdown 링크를 사용합니다.
- 코드 예시는 fenced code block 안에 둡니다. 설명의 파일명과 명령은 실제 파일·설정에 맞춥니다.
- `README.md` 인덱스는 사이트에서 각 폴더의 `index.html`로 변환합니다. 원본의 상대 `.md` 링크는 유지하고, 빌드 설정이 사이트 URL로 변환합니다. `docs/` 밖의 파일 링크는 GitHub 원본으로 연결합니다.
- `docs/.vitepress/dist/`와 `docs/.vitepress/cache/`는 생성 결과이며 커밋하지 않습니다. 문서는 `docs/` 원본에서만 수정합니다.
- 공개 저장소의 문서 사이트도 공개됩니다. 실제 비밀값·팀원의 개인정보·내부 계정 정보는 문서에 넣지 않습니다.

## 자동화

1. PR에서 `docs.yml`의 `Validate docs`가 CI·문서 도구 테스트와 원본 링크를 항상 검사합니다. [변경 영향 범위](testing.md#ci-scope)에 문서가 포함되면 VitePress 빌드와 생성 HTML의 내부 링크·앵커·자산 검사도 실행합니다. PR에서는 게시하지 않습니다.
2. 필수 검사와 [팀 작업 흐름](workflow.md)의 병합 기준을 충족해 `main`에 병합되면 전체 문서 검사를 실행하고 Pages 아티팩트를 만듭니다. 코드만 바뀐 경우에도 최신 원본 커밋을 일치시킵니다.
3. `Publish Pages`는 GitHub Pages에 정적 사이트를 배포합니다. `main`만 게시하며 이전 커밋의 수동 재실행은 최신 커밋 확인 후 게시를 건너뜁니다.
4. 사이트의 원본 커밋 링크로 게시 버전을 확인합니다. 게시 실패는 Actions에서 확인하고 원인 수정 후 최신 `main` 실행을 재시도합니다.

GitHub의 Settings → Pages → Source는 **GitHub Actions**로 설정합니다. 배포 환경 `github-pages`는 `main`만 허용합니다. 문서 변경 PR도 기본적으로 작성자 외 1명의 승인이 필요하며, 프로젝트 리더의 PR 검토 예외는 [팀 작업 흐름](workflow.md)을 따릅니다. 최초 사이트 URL은 첫 배포가 성공한 뒤 사용할 수 있습니다.

공개 저장소·표준 GitHub 호스팅 러너·기본 `github.io` 주소를 사용합니다. 별도 서버·유료 검색·도메인을 구입하지 않으며, Pages 아티팩트는 1일만 보관합니다. 작은 문서 사이트를 무료 저장량 한도 안에서 운영하는 구성입니다.

## 로컬 검사

저장소 루트에서 `.nvmrc`의 Node 22.22.1, npm 9.2.0, Python 3.13을 사용합니다. CI 도구 검사의 비밀번호 기호 표는 서버와 같은 Unicode 15.1을 사용하므로 Python 3.14 이상으로 대체하지 않습니다.

```bash
npm ci
python3 -m unittest discover -s scripts/tests -v
python3 scripts/check_docs.py
npm run docs:build
python3 scripts/check_docs_site.py
npm run docs:test-search
npm run docs:preview
```

미리보기 주소는 `http://localhost:4173/sku-dreamon/`입니다. 문서를 수정하며 보려면 `npm run docs:dev`를 실행하고 터미널에 표시된 `/sku-dreamon/` 주소로 접속합니다. 문서 설정·테마 변경 시 검색, 내부 링크, 좁은 화면의 메뉴도 확인합니다.

`docs:dev`는 VitePress 1.6.4의 로컬 검색 갱신 결함에 대한 `docs/.vitepress/patch-local-search.mjs` 패치를 설치된 모듈에 적용하며, `docs:test-search`와 문서 CI가 실제 파일 감시를 통해 제목·문서 추가/삭제·검색 제외·연속 편집을 검증합니다. 의존성 갱신 시 [#182](https://github.com/wejo-team/sku-dreamon/issues/182)의 임시 패치를 재검토하며, 정적 빌드는 패치 적용을 요구하지 않습니다.

VitePress는 안정 버전 1.6.4를 유지하고, 루트 `package.json`의 `overrides`로 Vite 6.4.5를 고정해 Vite·esbuild 의존성의 알려진 보안 권고를 해소합니다. VitePress 1.6.4의 기본 의존 범위는 Vite 5이지만, 이 문서 사이트는 data·path loader를 사용하지 않아 [관리자가 안내한 Vite 6 override 조건](https://github.com/vuejs/vitepress/issues/4494#issuecomment-2600813008)을 따릅니다. Vite 6.4는 [보안 패치를 받는 계열](https://vite.dev/releases#supported-versions)입니다.

개발 서버는 로컬에서 사용하며, 운영에는 빌드된 정적 파일만 배포합니다. 의존성 갱신 시 `npm ci`·`npm audit`, 빌드·원본 및 생성 링크 검사와 개발 서버·정적 미리보기의 검색·좁은 화면 메뉴·본문 HMR을 함께 확인합니다. 향후 VitePress 안정 버전이 수정된 Vite를 기본 지원하면 같은 검사를 거쳐 override를 제거합니다.

## 저장소 이름을 변경할 때

`docs/.vitepress/`의 GitHub 저장소 주소와 Pages `base`, 문서·템플릿의 저장소·사이트 주소, HTML 검사의 기본 `--base`와 관련 테스트를 함께 변경합니다. 패키지 이름은 저장소 이름과 별개로 관리하며, 현재 `sku-dreamon` 기반 이름은 그대로 사용합니다.

기존 로컬 저장소에서는 `origin`을 새 주소로 갱신합니다. 로컬 폴더 이름은 그대로 사용해도 됩니다.

```bash
git remote set-url origin https://github.com/wejo-team/sku-dreamon.git
```

주소·설정 변경 PR을 `develop`에 반영하고 해당 변경이 `main` 릴리스에 포함되어 `Publish Pages` 배포가 성공한 뒤, [새 문서 사이트](https://wejo-team.github.io/sku-dreamon/)에서 자산·하위 문서·검색·편집 링크를 확인합니다. GitHub 저장소 이름 변경만으로 Pages 게시 확인을 대신하지 않습니다.

## 근거

- [VitePress GitHub Pages 배포](https://vitepress.dev/guide/deploy#github-pages)
- [GitHub Pages 사용자 지정 workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Pages 이용 범위](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [GitHub Actions 요금 기준](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
