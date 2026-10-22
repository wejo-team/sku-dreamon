import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router';
import { AppShell } from '@/components/layout/AppShell';
import { queryClient } from '@/lib/query-client';
import { HealthPage } from '@/pages/HealthPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

// 페이지 구현 전 단계: 공통 AppShell 안에서 health 확인 화면과 404만 등록되어 있습니다.
// 하단 탭·로고의 목적지(/explore, /ai, /workspace, /profile)는 각 페이지 작업에서 라우트를 추가합니다.
export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route
            path="/"
            element={
              <AppShell>
                <HealthPage />
              </AppShell>
            }
          />
          <Route
            path="*"
            element={
              <AppShell>
                <NotFoundPage />
              </AppShell>
            }
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
