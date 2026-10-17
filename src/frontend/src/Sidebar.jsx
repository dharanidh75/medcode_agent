import { NavLink } from 'react-router-dom';
import { UploadCloud, ClipboardCheck } from 'lucide-react';

export default function Sidebar() {
  return (
    <div className="sidebar">
      <div className="sidebar-header">Discharge Coder</div>

      <div className="sidebar-nav">
        <NavLink
          to="/"
          end
          className={({ isActive }) => isActive ? "sidebar-link active" : "sidebar-link"}
        >
          <UploadCloud />
          Upload
        </NavLink>
        <NavLink
          to="/processed"
          className={({ isActive }) => isActive ? "sidebar-link active" : "sidebar-link"}
        >
          <ClipboardCheck />
          Processed Records
        </NavLink>
      </div>

      <div className="sidebar-spacer" />

      <div className="sidebar-footer">
        MedCode Coder Portal<br />v1.0
      </div>
    </div>
  );
}
