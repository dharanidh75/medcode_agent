import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { supabase } from './supabaseClient';
import {
  Search, FileText, ArrowUpRight, CheckCircle2, ClipboardCheck, Calendar, Clock
} from 'lucide-react';

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function ProcessedPage() {
  const [requests, setRequests] = useState([]);
  const [reviewedIds, setReviewedIds] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
        
        // Fetch done requests
        const reqRes = await fetch(`${backendUrl}/requests?status=done`);
        if (reqRes.ok) {
          const reqData = await reqRes.json();
          setRequests(reqData);
        }

        // Fetch reviewed status
        const corRes = await fetch(`${backendUrl}/corrections/reviewed-ids`);
        if (corRes.ok) {
          const corData = await corRes.json();
          setReviewedIds(new Set(corData.reviewed_ids));
        }
      } catch (err) {
        console.error("Error fetching processed data:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();

    // Subscribe to real-time updates via Supabase
    const channel = supabase.channel('processed-queue-changes')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'requests' }, (payload) => {
        const freshRow = payload.new;
        if (!freshRow || freshRow.status !== 'done') return;
        
        setRequests(prev => {
          const existingIds = new Set(prev.map(i => i.request_id));
          if (!existingIds.has(freshRow.request_id)) {
            return [freshRow, ...prev].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
          }
          return prev;
        });
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const totals = useMemo(() => {
    let concepts = 0;
    requests.forEach((r) => {
      concepts += (r.results || []).length;
    });
    return { records: requests.length, concepts };
  }, [requests]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return requests;
    return requests.filter((r) => {
      if (r.request_id?.toLowerCase().includes(q)) return true;
      if (r.filename?.toLowerCase().includes(q)) return true;
      return (r.results || []).some((res) =>
        res.matched_code?.toLowerCase().includes(q) ||
        res.matched_description?.toLowerCase().includes(q) ||
        res.concept?.toLowerCase().includes(q)
      );
    });
  }, [requests, query]);

  if (loading) {
    return (
      <div className="page-container">
        <p className="page-subtitle" style={{ marginTop: '2rem' }}>Loading processed records…</p>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Processed Records</h1>
        <p className="page-subtitle">Queue of documents successfully coded by AI, awaiting your review.</p>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <span className="stat-value">{totals.records}</span>
          <span className="stat-label">Records coded</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{totals.concepts}</span>
          <span className="stat-label">Total Concepts Extracted</span>
        </div>
      </div>

      <div className="search-bar">
        <Search size={16} />
        <input
          type="text"
          placeholder="Search by filename, request ID, or code…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state upload-empty-state">
          <ClipboardCheck size={28} />
          <p>{requests.length === 0 ? 'No documents have been processed yet.' : 'No records match your search.'}</p>
          {requests.length === 0 && (
            <Link className="btn-secondary" to="/" style={{ marginTop: '1rem' }}>Upload a document</Link>
          )}
        </div>
      ) : (
        <div className="upload-queue-list" style={{ marginTop: '1rem' }}>
          {filtered.map((req) => {
            const isReviewed = reviewedIds.has(req.request_id);
            const totalCodes = (req.results || []).length;
            
            return (
              <div key={req.request_id} className="upload-queue-item" style={{ padding: '1rem' }}>
                <div className="upload-queue-file-icon">
                  <FileText size={17} />
                </div>

                <div className="upload-queue-info">
                  <div className="upload-queue-name">{req.filename || 'Discharge Document'}</div>
                  <div className="upload-queue-meta">
                    <Calendar size={11} style={{marginRight: 4, display: 'inline-block'}}/>
                    {formatDate(req.created_at)}
                    <span className="upload-queue-reqid"> · {req.request_id}</span>
                  </div>
                </div>
                
                <div className="upload-queue-result" style={{ marginRight: '1rem', minWidth: '100px' }}>
                  {totalCodes} code{totalCodes !== 1 ? 's' : ''} found
                </div>

                {isReviewed ? (
                  <div className="badge done upload-queue-badge">
                    <CheckCircle2 size={12} />
                    Reviewed
                  </div>
                ) : (
                  <div className="badge pending upload-queue-badge" style={{ backgroundColor: '#fff3cd', color: '#856404' }}>
                    <Clock size={12} />
                    Needs Review
                  </div>
                )}

                <div className="upload-queue-actions">
                  <Link className="btn-secondary btn-small" to={`/review/${req.request_id}`} style={{ marginLeft: '1rem' }}>
                    {isReviewed ? 'Edit Review' : 'Start Review'}
                    <ArrowUpRight size={13} />
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
