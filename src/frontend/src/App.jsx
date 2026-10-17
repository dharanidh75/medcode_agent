import { Routes, Route } from 'react-router-dom';
import { Activity, Bell, HelpCircle } from 'lucide-react';
import Sidebar from './Sidebar';
import UploadPage from './UploadPage';
import ProcessedPage from './ProcessedPage';
import ReviewPage from './ReviewPage';

function App() {
  return (
    <div className="app-container">
      {/* Topbar */}
      <div className="topbar">
        <div className="topbar-brand">
          <div className="topbar-logo">
            <Activity size={17} strokeWidth={2.5} />
          </div>
          <span className="topbar-wordmark">MedCode</span>
          <span className="topbar-tag">Coder Portal</span>
        </div>

        <div className="topbar-actions">
          <button className="icon-btn" title="Help" type="button">
            <HelpCircle size={17} />
          </button>
          <button className="icon-btn" title="Notifications" type="button">
            <Bell size={17} />
          </button>
          <div className="topbar-user">
            <div className="topbar-user-avatar">PS</div>
            <div className="topbar-user-info">
              <span className="topbar-user-name">Priya S.</span>
              <span className="topbar-user-role">Medical Coder</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Layout containing Sidebar and Content */}
      <div className="main-layout">
        <Sidebar />

        <div className="content-area">
          <Routes>
            <Route path="/" element={<UploadPage />} />
            <Route path="/processed" element={<ProcessedPage />} />
            <Route path="/review/:requestId" element={<ReviewPage />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}

export default App;
