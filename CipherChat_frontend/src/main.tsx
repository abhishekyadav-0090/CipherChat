import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MotionConfig } from 'framer-motion';
import App from './App';
import './index.css';

const container = document.getElementById('root');
if (!container) throw new Error('Root element missing');

createRoot(container).render(
  <StrictMode>
    {/* reducedMotion="user" makes every framer-motion animation honour the OS setting */}
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </StrictMode>,
);
