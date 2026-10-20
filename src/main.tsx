import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Base styles first: the per-area sheets imported by components must load after them to override.
import './styles.css';
import App from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
