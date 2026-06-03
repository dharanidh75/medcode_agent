import React, { useState, useEffect, useRef } from 'react';
import './App.css';

const API_BASE = 'http://localhost:8000/api/v1';

// ── Case Card Component ────────────────────────────────────────────────────────
function CaseCard({ c, borderClass, statusClass, statusLabel }) {
  const icd10 = c.icd10_codes
    ? (Array.isArray(c.icd10_codes) ? c.icd10_codes : JSON.parse(c.icd10_codes)).join(', ')
    : '—';
  const cpt = c.cpt_codes
    ? (Array.isArray(c.cpt_codes) ? c.cpt_codes : JSON.parse(c.cpt_codes)).join(', ')
    : '—';

  return (
    <div className={`case-rectangle-box ${borderClass}`}>
      <div className="case-header">
        <strong>Case #{c.id.split('-')[0].toUpperCase()}</strong>
        <span className={`case-status ${statusClass}`}>{statusLabel}</span>
      </div>
      <div className="case-body">
        <p><strong>Patient:</strong> {c.patient_name} | <strong>Provider:</strong> {c.doctor_name}</p>
        <p><strong>ICD-10:</strong> {icd10} | <strong>CPT:</strong> {cpt}</p>
        <p><strong>Retries:</strong> {c.retry_count} | <strong>Insurance:</strong> {c.insurance_no || 'N/A'}</p>
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
function App() {
  const [currentView, setCurrentView] = useState('form');
  const [formData, setFormData] = useState({
    hospitalName: '', doctorName: '', patientName: '',
    patientDob: '', patientGender: '', insuranceProvider: '',
    insuranceNo: '', groupNo: '', clinicalNotes: '',
  });

  // OCR state
  const [isOcrLoading, setIsOcrLoading] = useState(false);
  const [ocrMessage, setOcrMessage] = useState('');
  const fileInputRef = useRef(null);

  // Pipeline SSE state
  const [pipelineEvents, setPipelineEvents] = useState([]);
  const [isPipelineRunning, setIsPipelineRunning] = useState(false);
  const [pipelineResult, setPipelineResult] = useState(null);

  // Case ledger state
  const [pendingCases, setPendingCases] = useState([]);
  const [acceptedCases, setAcceptedCases] = useState([]);
  const [rejectedCases, setRejectedCases] = useState([]);
  const [casesLoading, setCasesLoading] = useState(false);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const isFormIncomplete = Object.values(formData).some(v => !v.trim());

  // ── OCR Upload ────────────────────────────────────────────────────────────
  const handleFileSelect = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsOcrLoading(true);
    setOcrMessage('Running PaddleOCR and parsing document...');

    const payload = new FormData();
    payload.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/ocr-upload`, {
        method: 'POST',
        body: payload,
      });
      const data = await res.json();

      if (!res.ok) throw new Error(data.detail || 'OCR failed');

      if (data.success) {
        setFormData(prev => ({ ...prev, ...data.data }));
        setOcrMessage(data.message || 'Document auto-filled. Please review.');
      } else {
        setOcrMessage(data.message || 'OCR could not extract text. Please fill manually.');
      }
    } catch (err) {
      setOcrMessage(`OCR error: ${err.message}`);
    } finally {
      setIsOcrLoading(false);
      // Reset file input so the same file can be re-selected
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  // ── Pipeline Execution (SSE) ───────────────────────────────────────────────
  const handleContinue = async () => {
    if (isFormIncomplete) {
      alert('Please fill in all required fields before continuing.');
      return;
    }

    setPipelineEvents([]);
    setPipelineResult(null);
    setIsPipelineRunning(true);

    try {
      const res = await fetch(`${API_BASE}/execute-pipeline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Pipeline failed to start');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data:')) {
            try {
              const eventData = JSON.parse(line.slice(5).trim());
              setPipelineEvents(prev => [...prev, eventData]);

              if (eventData.event === 'complete') {
                setPipelineResult(eventData.data);
                setIsPipelineRunning(false);
                const dest = eventData.data?.final_status === 'accepted' ? 'accepted' : 'pending';
                setTimeout(() => {
                  fetchCases(dest);
                  setCurrentView(dest);
                }, 800);
              } else if (eventData.event === 'error') {
                setIsPipelineRunning(false);
              }
            } catch (_) {
              // Ignore parse errors on malformed SSE chunks
            }
          }
        }
      }
    } catch (err) {
      setPipelineEvents(prev => [...prev, {
        event: 'error',
        status: 'failed',
        message: `Connection error: ${err.message}`,
      }]);
      setIsPipelineRunning(false);
    }
  };

  // ── Fetch Case Ledgers ────────────────────────────────────────────────────
  const fetchCases = async (view) => {
    setCasesLoading(true);
    try {
      const res = await fetch(`${API_BASE}/${view}`);
      const data = await res.json();
      if (view === 'pending') setPendingCases(data);
      else if (view === 'accepted') setAcceptedCases(data);
      else if (view === 'rejected') setRejectedCases(data);
    } catch (err) {
      console.error(`Failed to fetch ${view} cases:`, err);
    } finally {
      setCasesLoading(false);
    }
  };

  useEffect(() => {
    if (['pending', 'accepted', 'rejected'].includes(currentView)) {
      fetchCases(currentView);
    }
  }, [currentView]);

  // ── Render Views ──────────────────────────────────────────────────────────
  const renderContent = () => {
    switch (currentView) {
      case 'form':
        return (
          <center>
            <div className="form-workspace">
              <h2>Medical Coding Form</h2>
              <p>Fill out the patient case details below.</p>

              {/* OCR Upload */}
              <div className="upload-box">
                <p>Upload Medical Note / Chart Scan to Auto-Fill Form</p>
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileSelect}
                  accept="image/jpeg,image/png,image/tiff,image/bmp,image/webp,application/pdf"
                  style={{ display: 'none' }}
                />
                <button
                  type="button"
                  onClick={handleUploadClick}
                  className="upload-btn"
                  disabled={isOcrLoading}
                >
                  {isOcrLoading ? (
                    <><span className="pipeline-spinner" style={{ width: 14, height: 14 }} /> Processing...</>
                  ) : (
                    <span>Upload Image</span>
                  )}
                </button>
                {ocrMessage && (
                  <p style={{ marginTop: 10, fontSize: '0.85rem', color: '#475569' }}>
                    {ocrMessage}
                  </p>
                )}
              </div>

              {isFormIncomplete && (
                <div className="alert-box">
                  <strong>Attention Required:</strong> Missing critical details. Please review and fill out the fields marked in yellow.
                </div>
              )}

              <form className="medical-form">
                <div className="form-section">
                  <h3>Facility &amp; Provider Information</h3>
                  <div className="form-grid">
                    <input type="text" name="hospitalName" value={formData.hospitalName} onChange={handleInputChange} placeholder="Hospital Name" className={!formData.hospitalName ? 'highlight-input' : ''} />
                    <input type="text" name="doctorName" value={formData.doctorName} onChange={handleInputChange} placeholder="Doctor Name" className={!formData.doctorName ? 'highlight-input' : ''} />
                  </div>
                </div>

                <div className="form-section">
                  <h3>Patient Demographics</h3>
                  <div className="form-grid">
                    <input type="text" name="patientName" value={formData.patientName} onChange={handleInputChange} placeholder="Patient Full Name" className={!formData.patientName ? 'highlight-input' : ''} />
                    <input type="date" name="patientDob" value={formData.patientDob} onChange={handleInputChange} className={!formData.patientDob ? 'highlight-input' : ''} />
                    <select name="patientGender" value={formData.patientGender} onChange={handleInputChange} className={!formData.patientGender ? 'highlight-input' : ''}>
                      <option value="">Select Gender</option>
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>
                </div>

                <div className="form-section">
                  <h3>Insurance &amp; Code Mapping Details</h3>
                  <div className="form-grid">
                    <input type="text" name="insuranceProvider" value={formData.insuranceProvider} onChange={handleInputChange} placeholder="Insurance Provider" className={!formData.insuranceProvider ? 'highlight-input' : ''} />
                    <input type="text" name="insuranceNo" value={formData.insuranceNo} onChange={handleInputChange} placeholder="Insurance No / Policy ID *" className={!formData.insuranceNo ? 'highlight-input' : ''} />
                    <input type="text" name="groupNo" value={formData.groupNo} onChange={handleInputChange} placeholder="Group Number" className={!formData.groupNo ? 'highlight-input' : ''} />
                  </div>
                </div>

                <div className="form-section">
                  <h3>Clinical Narrative</h3>
                  <textarea name="clinicalNotes" value={formData.clinicalNotes} onChange={handleInputChange} placeholder="Physician Notes, Diagnosis, and Procedures..." rows="5" className={!formData.clinicalNotes ? 'highlight-input' : ''}></textarea>
                </div>

                <div className="submit-btn-container">
                  <button
                    type="button"
                    className="submit-btn"
                    onClick={handleContinue}
                    disabled={isPipelineRunning}
                  >
                    {isPipelineRunning ? 'Processing...' : 'Continue'}
                  </button>
                </div>
              </form>
            </div>
          </center>
        );

      case 'pending':
        return (
          <center>
            <div>
              <h2>Pending Approvals</h2>
              {casesLoading ? <p>Loading...</p> : pendingCases.length === 0 ? (
                <p style={{ color: '#94a3b8' }}>No pending cases.</p>
              ) : pendingCases.map(c => (
                <CaseCard key={c.id} c={c} borderClass="warning-border" statusClass="text-warning" statusLabel="Pending" />
              ))}
            </div>
          </center>
        );

      case 'accepted':
        return (
          <center>
            <div>
              <h2>Accepted Cases</h2>
              {casesLoading ? <p>Loading...</p> : acceptedCases.length === 0 ? (
                <p style={{ color: '#94a3b8' }}>No accepted cases.</p>
              ) : acceptedCases.map(c => (
                <CaseCard key={c.id} c={c} borderClass="success-border" statusClass="text-success" statusLabel="Approved" />
              ))}
            </div>
          </center>
        );

      case 'rejected':
        return (
          <center>
            <div>
              <h2>Rejected Cases</h2>
              {casesLoading ? <p>Loading...</p> : rejectedCases.length === 0 ? (
                <p style={{ color: '#94a3b8' }}>No rejected cases.</p>
              ) : rejectedCases.map(c => (
                <CaseCard key={c.id} c={c} borderClass="danger-border" statusClass="text-danger" statusLabel="Rejected" />
              ))}
            </div>
          </center>
        );

      default:
        return <h2>Welcome to MedCode</h2>;
    }
  };

  return (
    <div className="App">
      <nav className="navbar">
        <h1>MedCode</h1>
      </nav>
      <div className="body">
        <div className="sidebar">
          <ul>
            {['form', 'pending', 'accepted', 'rejected'].map(view => (
              <li
                key={view}
                className={currentView === view ? 'active' : ''}
                onClick={() => setCurrentView(view)}
              >
                {view.charAt(0).toUpperCase() + view.slice(1)}
              </li>
            ))}
          </ul>
        </div>
        <div className="content">{renderContent()}</div>
      </div>
    </div>
  );
}

export default App;