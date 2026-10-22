import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router';
import { queryClient } from '@/lib/query-client';
import { HealthPage } from '@/pages/HealthPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { AppShell } from '@/components/layout/AppShell';

{/*가상 수행 영역 (테스트 코드) */ }
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

{/*실제 수행 영역 (실제 수정해야할 영역) */ }
{/*export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HealthPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}*/}
