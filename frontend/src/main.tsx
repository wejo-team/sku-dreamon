import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '@/app/App';
import '@/styles/globals.css';
// 공식 화면 스타일(design-reference/src/features/design-preview/*.css)을 원본과 같은 순서로 불러옵니다.
import '@/styles/mascot-profile.css';
import '@/styles/workspace.css';
import '@/styles/login.css';
import '@/styles/profile-fields.css';
import '@/styles/design-preview.css';
import '@/styles/service-ui.css';
import '@/styles/applicant-assessment.css';
import '@/styles/information-hierarchy.css';
import '@/styles/mobile-preview.css';

const root = document.getElementById('root');
if (!root) throw new Error('Root element was not found');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
