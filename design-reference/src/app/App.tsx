import { BrowserRouter, Navigate, Route, Routes } from 'react-router';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { DesignPreviewPage } from '@/pages/DesignPreviewPage';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            <Navigate
              replace
              to="/design-preview/login?returnTo=%2Fdesign-preview%2Fexplore"
            />
          }
        />
        <Route path="/design-preview/*" element={<DesignPreviewPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
