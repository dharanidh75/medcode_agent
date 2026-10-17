import { useEffect, useRef, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { supabase } from './supabaseClient';
import {
  Paperclip, FileText, FileImage, X, RotateCw, ArrowUpRight, SendHorizontal,
  Loader2, Clock, CheckCircle2, XCircle, Stethoscope
} from 'lucide-react';

// Expected backend contract:
// POST {backendUrl}/upload  (multipart, field name "file")
//   -> { "request_id": "...", "status": "pending" }
// The backend then processes the document asynchronously (OCR/text extraction,
// diagnosis + procedure identification, ICD-10-CM / ICD-10-PCS code matching)
// and writes/updates a row in the Supabase "requests" table:
//   request_id, status ('pending' | 'processing' | 'done' | 'failed'),
//   raw_input, results: [{ category: 'diagnosis' | 'procedure', concept,
//   source_span, matched_code, matched_description }], error_message, created_at
// This page listens for those row changes over Supabase realtime.

const ACCEPTED = 'image/*,.pdf,.doc,.docx,.txt';

const STATUS_META = {
  uploading: { label: 'Uploading', icon: Loader2, spin: true, cls: 'pending' },
  pending: { label: 'Queued', icon: Clock, spin: false, cls: 'pending' },
  processing: { label: 'Extracting codes', icon: Loader2, spin: true, cls: 'processing' },
  done: { label: 'Done', icon: CheckCircle2, spin: false, cls: 'done' },
  failed: { label: 'Failed', icon: XCircle, spin: false, cls: 'failed' },
};

function fileTypeIcon(file) {
  if (file?.type?.startsWith('image/')) return FileImage;
  return FileText;
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function makeId() {
  return `q_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function makeStagedId() {
  return `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function splitResults(results) {
  const diagnoses = [];
  const procedures = [];
  (results || []).forEach((r) => {
    if ((r.category || '').toLowerCase().startsWith('proc')) procedures.push(r);
    else diagnoses.push(r);
  });
  return { diagnoses, procedures };
}

export default function UploadPage() {
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [staged, setStaged] = useState([]); // files attached but not yet submitted
  const [queue, setQueue] = useState([]); // session upload queue (submitted)

  useEffect(() => {
    // Fetch all uploads from the backend database on mount
    const fetchRecentQueue = async () => {
      try {
        const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
        const response = await fetch(`${backendUrl}/requests`);
        if (!response.ok) throw new Error('Failed to fetch');
        
        const data = await response.json();
        const historicalQueue = data.map(row => {
          const { diagnoses, procedures } = splitResults(row.results);
          return {
            localId: row.request_id,
            file: null,
            name: row.filename || 'Unknown Document',
            size: 0,
            status: row.status,
            requestId: row.request_id,
            error: row.error_message || null,
            diagCount: diagnoses.length,
            procCount: procedures.length,
          };
        });
        setQueue(historicalQueue);
      } catch (error) {
        console.error("Error fetching historical queue:", error);
      }
    };
    
    fetchRecentQueue();
  }, []);

  const uploadOne = useCallback(async (file) => {
    const localId = makeId();

    setQueue((prev) => [
      { localId, file, name: file.name, size: file.size, status: 'uploading', requestId: null, error: null, diagCount: 0, procCount: 0 },
      ...prev,
    ]);

    try {
      const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
      const body = new FormData();
      body.append('file', file);

      const response = await fetch(`${backendUrl}/upload`, {
        method: 'POST',
        body,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Upload failed');
      }

      const data = await response.json();
      const requestId = data.request_id || data.id;

      setQueue((prev) => {
        // Handle race condition: if realtime listener already added this request_id
        const alreadyExists = prev.some(item => item.requestId === requestId && item.localId !== localId);
        if (alreadyExists) {
           return prev.map(item => {
               if (item.requestId === requestId) {
                   return { ...item, file, size: file.size, name: file.name };
               }
               return item;
           }).filter(item => item.localId !== localId);
        }
        
        return prev.map((item) => (
          item.localId === localId
            ? { ...item, requestId, status: data.status || 'pending' }
            : item
        ));
      });
    } catch (err) {
      setQueue((prev) => prev.map((item) => (
        item.localId === localId
          ? { ...item, status: 'failed', error: err.message }
          : item
      )));
    }
  }, []);

  const handleFiles = (fileList) => {
    const files = Array.from(fileList || []);
    if (files.length === 0) return;
    setStaged((prev) => [
      ...prev,
      ...files.map((file) => ({ stagedId: makeStagedId(), file, name: file.name, size: file.size })),
    ]);
  };

  const removeStagedFile = (stagedId) => {
    setStaged((prev) => prev.filter((f) => f.stagedId !== stagedId));
  };

  const handleSubmit = () => {
    if (staged.length === 0) return;
    staged.forEach((item) => uploadOne(item.file));
    setStaged([]);
  };

  const retryItem = (localId) => {
    const item = queue.find((q) => q.localId === localId);
    if (!item) return;
    setQueue((prev) => prev.filter((q) => q.localId !== localId));
    uploadOne(item.file);
  };

  const dismissItem = (localId) => {
    setQueue((prev) => prev.filter((q) => q.localId !== localId));
  };

  // Subscribe to real-time updates via Supabase
  useEffect(() => {
    const channel = supabase.channel('upload-queue-changes')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'requests' }, (payload) => {
        const freshRow = payload.new;
        if (!freshRow || !freshRow.request_id) return;

        setQueue(prev => {
          let updated = false;
          
          const nextQueue = prev.map(item => {
             if (item.requestId === freshRow.request_id) {
                 if (freshRow.status !== item.status || (freshRow.status === 'done' && (item.diagCount === 0 && item.procCount === 0))) {
                    const { diagnoses, procedures } = splitResults(freshRow.results);
                    updated = true;
                    return {
                      ...item,
                      status: freshRow.status,
                      error: freshRow.error_message || null,
                      diagCount: diagnoses.length,
                      procCount: procedures.length,
                    };
                 }
             }
             return item;
          });
          
          // Check for brand new items from other tabs/users
          const existingIds = new Set(prev.map(i => i.requestId));
          if (!existingIds.has(freshRow.request_id)) {
            const { diagnoses, procedures } = splitResults(freshRow.results);
            const newItem = {
              localId: freshRow.request_id,
              file: null,
              name: freshRow.filename || 'Unknown Document',
              size: 0,
              status: freshRow.status,
              requestId: freshRow.request_id,
              error: freshRow.error_message || null,
              diagCount: diagnoses.length,
              procCount: procedures.length,
            };
            updated = true;
            return [newItem, ...nextQueue].sort((a, b) => b.localId.localeCompare(a.localId));
          }
          
          return updated ? nextQueue : prev;
        });
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const activeCount = queue.filter((q) => ['uploading', 'pending', 'processing'].includes(q.status)).length;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Upload Discharge Documents</h1>
        <p className="page-subtitle">Attach a chart, discharge summary, or scanned note, then submit — codes are extracted automatically.</p>
      </div>

      <div
        className={`composer ${isDragging ? 'is-dragging' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        {staged.length > 0 && (
          <div className="composer-attachments">
            {staged.map((item) => {
              const FileIcon = fileTypeIcon(item.file);
              return (
                <div key={item.stagedId} className="composer-chip">
                  <FileIcon size={14} />
                  <span className="composer-chip-name">{item.name}</span>
                  <span className="composer-chip-size">{formatSize(item.size)}</span>
                  <button
                    className="composer-chip-remove"
                    type="button"
                    title="Remove"
                    onClick={() => removeStagedFile(item.stagedId)}
                  >
                    <X size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <div className="composer-row">
          <button className="icon-btn composer-attach-btn" type="button" title="Attach files" onClick={() => fileInputRef.current?.click()}>
            <Paperclip size={18} />
          </button>
          <div className="composer-placeholder">
            {staged.length > 0
              ? `${staged.length} file${staged.length !== 1 ? 's' : ''} attached — add more or submit for coding`
              : 'Attach discharge documents — PDFs, images, or scans — then submit for coding'}
          </div>
          <button
            className="composer-submit-btn"
            type="button"
            title="Submit for coding"
            disabled={staged.length === 0}
            onClick={handleSubmit}
          >
            <SendHorizontal size={17} />
          </button>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED}
          hidden
          multiple
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      <div className="queue-section-header">
        <h2 className="section-heading">Upload Queue</h2>
        {activeCount > 0 && (
          <span className="section-heading-badge">{activeCount} in progress</span>
        )}
      </div>

      {queue.length === 0 ? (
        <div className="empty-state upload-empty-state">
          <Stethoscope size={28} />
          <p>Nothing uploaded yet this session. Add a document above to get started.</p>
        </div>
      ) : (
        <div className="upload-queue-list">
          {queue.map((item) => {
            const meta = STATUS_META[item.status] || STATUS_META.pending;
            const StatusIcon = meta.icon;
            const FileIcon = fileTypeIcon(item.file);
            return (
              <div key={item.localId} className="upload-queue-item">
                <div className="upload-queue-file-icon">
                  <FileIcon size={17} />
                </div>

                <div className="upload-queue-info">
                  <div className="upload-queue-name">{item.name}</div>
                  <div className="upload-queue-meta">
                    {item.size > 0 && <span>{formatSize(item.size)}</span>}
                    {item.requestId && (
                      <span className="upload-queue-reqid">{item.size > 0 ? ' · ' : ''}{item.requestId}</span>
                    )}
                  </div>
                  {item.status === 'failed' && item.error && (
                    <div className="upload-queue-error">{item.error}</div>
                  )}
                </div>

                <div className={`badge ${meta.cls} upload-queue-badge`}>
                  <StatusIcon size={12} className={meta.spin ? 'spin' : ''} />
                  {meta.label}
                </div>

                {item.status === 'done' && (
                  <div className="upload-queue-result">
                    {item.diagCount + item.procCount} code{item.diagCount + item.procCount !== 1 ? 's' : ''} found
                  </div>
                )}

                <div className="upload-queue-actions">
                  {item.status === 'done' && item.requestId && (
                    <Link className="icon-btn" to={`/review/${item.requestId}`} title="View codes">
                      <ArrowUpRight size={16} />
                    </Link>
                  )}
                  {item.status === 'failed' && (
                    <button className="icon-btn" type="button" title="Retry" onClick={() => retryItem(item.localId)}>
                      <RotateCw size={15} />
                    </button>
                  )}
                  <button className="icon-btn" type="button" title="Remove" onClick={() => dismissItem(item.localId)}>
                    <X size={15} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {queue.some((q) => q.status === 'done') && (
        <div className="upload-queue-footer">
          <Link className="btn-secondary" to="/processed">
            View all in Processed Records
            <ArrowUpRight size={15} />
          </Link>
        </div>
      )}
    </div>
  );
}
