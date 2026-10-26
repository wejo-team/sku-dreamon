/**
 * [참조 출처]
 * 1. design-reference/src/pages/DesignPreviewPage.tsx - 화면 경로와 공통 Provider·Shell 연결 원본
 * 2. docs/design/screens.md - 「화면별 참조」 15개 화면 경로
 * 3. docs/design/handoff.md - /design-preview 접두사는 개발용 식별자, 메모리 상태는 서버 계약이 아님
 * 4. docs/development/frontend.md - 「화면과 상태」 라우트 화면은 pages/, 서버 데이터는 TanStack Query
 * 5. docs/api/catalogs.md#catalog-endpoints - 화면 전체가 쓰는 공통 선택지를 먼저 조회
 */

import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Outlet, Route, Routes } from 'react-router';
import { AppShell } from '@/components/layout/AppShell';
import {
  LoginPage,
  ProfilePage,
  PublicProfilePage,
  SignupPage,
} from '@/features/account/AccountPages';
import { AiChatPage, AiChatProvider } from '@/features/ai/AiChatPage';
import { CatalogGate } from '@/features/catalogs/CatalogGate';
import {
  ContestPage,
  ExplorePage,
  PersonPage,
} from '@/features/explore/ExplorePages';
import { ApplicantReviewProvider } from '@/features/teams/ApplicantReviewProvider';
import { CreateTeamPage } from '@/features/teams/CreateTeamPage';
import {
  ApplicantPage,
  TeamPage,
  WorkspacePage,
} from '@/features/workspace/WorkspacePages';
import { queryClient } from '@/lib/query-client';
import { HealthPage } from '@/pages/HealthPage';
import { LoadingPage } from '@/pages/LoadingPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import {
  ReferenceNoticePage,
  ReferencePortfolioPage,
} from '@/pages/ReferencePages';

// [출처 4, 5] 서버 데이터는 각 화면이 TanStack Query로 조회합니다(VITE_API_MOCK이면 목업 서버).
// AI 대화·지원자 검토는 API 미구현이라 화면 데모 상태만 이 범위에서 공유합니다.
function ServiceLayout() {
  return (
    <div className="dreamon-mobile-viewport">
      <CatalogGate>
        <AiChatProvider>
          <ApplicantReviewProvider>
            <Outlet />
          </ApplicantReviewProvider>
        </AiChatProvider>
      </CatalogGate>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* 백엔드 연결 확인 화면은 서비스 Shell 밖에 둡니다. */}
          <Route path="/health" element={<HealthPage />} />
          <Route element={<ServiceLayout />}>
            {/* [출처 2] 시작 안내 */}
            <Route index element={<LoadingPage />} />
            <Route path="loading" element={<LoadingPage />} />
            <Route element={<AppShell />}>
              {/* [출처 1] 실제 기관·개인 사이트를 대신하는 로컬 링크 목적지 */}
              <Route
                path="reference/notices/:contestId"
                element={<ReferenceNoticePage />}
              />
              <Route
                path="reference/portfolios/:personId"
                element={<ReferencePortfolioPage />}
              />
              {/* [출처 2] 탐색·상세 */}
              <Route path="explore" element={<ExplorePage />} />
              <Route path="contests/:contestId" element={<ContestPage />} />
              <Route path="people/:personId" element={<PersonPage />} />
              {/* [출처 2] AI */}
              <Route path="ai" element={<AiChatPage />} />
              {/* [출처 2] 워크스페이스·팀·지원자 */}
              <Route path="workspace" element={<WorkspacePage />} />
              <Route path="teams/new" element={<CreateTeamPage />} />
              <Route path="teams/:teamId" element={<TeamPage />} />
              <Route
                path="applicants/:applicantId"
                element={<ApplicantPage />}
              />
              {/* [출처 2] 계정·프로필 */}
              <Route path="profile" element={<ProfilePage />} />
              <Route path="profile/public" element={<PublicProfilePage />} />
              <Route path="login" element={<LoginPage />} />
              <Route path="signup" element={<SignupPage />} />
              {/* [출처 1, 2] 정의되지 않은 경로 */}
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
