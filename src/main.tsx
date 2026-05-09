import { createRoot } from 'react-dom/client';
import { bootstrapGeneratedSiteAnalytics } from './analytics.ts';
import App from './App.tsx';
import './index.css';

bootstrapGeneratedSiteAnalytics();

createRoot(document.getElementById('root')!).render(<App />);
