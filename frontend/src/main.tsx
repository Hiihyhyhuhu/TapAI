import React from 'react';
import ReactDOM from 'react-dom/client';
import SidePanel from './components/SidePanel';
// @ts-expect-error CSS is resolved by the bundler, not TypeScript.
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <SidePanel />
  </React.StrictMode>
);