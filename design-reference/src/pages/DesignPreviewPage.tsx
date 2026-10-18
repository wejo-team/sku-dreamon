import { Route, Routes } from 'react-router';
import { PreviewProvider } from '@/features/design-preview/PreviewProvider';
import { PreviewShell } from '@/features/design-preview/PreviewShell';
import { LoadingPage } from '@/features/design-preview/LoadingPage';
import {
  ContestPage,
  ExplorePage,
  PersonPage,
} from '@/features/design-preview/ExplorePages';
import {
  ApplicantPage,
  TeamPage,
  WorkspacePage,
} from '@/features/design-preview/WorkspacePages';
import {
  LoginPage,
  ProfilePage,
  PublicProfilePage,
  SignupPage,
} from '@/features/design-preview/AccountPages';
import { ActionLink, EmptyState } from '@/features/design-preview/PreviewUi';
import { CreateTeamPage } from '@/features/design-preview/CreateTeamPage';
import {
  ReferenceNoticePage,
  ReferencePortfolioPage,
} from '@/features/design-preview/ReferencePages';
import { previewPath } from '@/features/design-preview/data';
import {
  AiChatPage,
  AiChatProvider,
} from '@/features/design-preview/AiChatPage';
import '@/features/design-preview/design-preview.css';
import '@/features/design-preview/service-ui.css';
import '@/features/design-preview/mobile-preview.css';

export function DesignPreviewPage() {
  return (
    <div className="dreamon-mobile-viewport">
      <PreviewProvider>
        <AiChatProvider>
          <Routes>
            <Route index element={<LoadingPage />} />
            <Route path="loading" element={<LoadingPage />} />
            <Route element={<PreviewShell />}>
              <Route
                path="reference/notices/:contestId"
                element={<ReferenceNoticePage />}
              />
              <Route
                path="reference/portfolios/:personId"
                element={<ReferencePortfolioPage />}
              />
              <Route path="explore" element={<ExplorePage />} />
              <Route path="ai" element={<AiChatPage />} />
              <Route path="contests/:contestId" element={<ContestPage />} />
              <Route path="people/:personId" element={<PersonPage />} />
              <Route path="workspace" element={<WorkspacePage />} />
              <Route path="teams/new" element={<CreateTeamPage />} />
              <Route path="teams/:teamId" element={<TeamPage />} />
              <Route
                path="applicants/:applicantId"
                element={<ApplicantPage />}
              />
              <Route path="profile" element={<ProfilePage />} />
              <Route path="profile/public" element={<PublicProfilePage />} />
              <Route path="login" element={<LoginPage />} />
              <Route path="signup" element={<SignupPage />} />
              <Route
                path="*"
                element={
                  <EmptyState
                    title="페이지를 찾을 수 없어요"
                    description="탐색으로 돌아가 다시 시작해 주세요."
                  >
                    <ActionLink to={previewPath('/explore')}>
                      탐색으로
                    </ActionLink>
                  </EmptyState>
                }
              />
            </Route>
          </Routes>
        </AiChatProvider>
      </PreviewProvider>
    </div>
  );
}
