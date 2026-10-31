import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '@/app/App';
import '@/styles/globals.css';
// 제품 화면의 공통 스타일과 기능별 스타일을 순서대로 불러옵니다.
import '@/styles/mascot-profile.css';
import '@/styles/workspace.css';
import '@/styles/login.css';
import '@/styles/profile-fields.css';
import '@/styles/design-preview.css';
import '@/styles/service-ui.css';
import '@/styles/applicant-assessment.css';
import '@/styles/ai-results.css';
import '@/styles/information-hierarchy.css';
import '@/styles/mobile-preview.css';
import '@/styles/explore-layout.css';
import '@/styles/team-cards.css';

const root = document.getElementById('root');
if (!root) throw new Error('Root element was not found');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
