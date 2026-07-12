import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout';
import { Dashboard } from './pages/Dashboard';
import { Expenses } from './pages/Expenses';
import { Planning } from './pages/Planning';
import { Goals } from './pages/Goals';
import { Reporting } from './pages/Reporting';
import { AppSettings } from './pages/Settings';

import { ToastProvider } from './contexts/ToastContext';

function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="expenses"  element={<Expenses />} />
            <Route path="planning"  element={<Planning />} />
            <Route path="goals"     element={<Goals />} />
            <Route path="reporting" element={<Reporting />} />
            <Route path="settings"  element={<AppSettings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
