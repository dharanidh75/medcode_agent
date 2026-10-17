import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { supabase } from './supabaseClient';
import { ArrowLeft, Stethoscope, Scissors, Copy, Check, Edit2, Flag, Undo2 } from 'lucide-react';

export default function ReviewPage() {
  const { requestId } = useParams();
  const navigate = useNavigate();
  
  const [request, setRequest] = useState(null);
  const [localResults, setLocalResults] = useState([]);
  const [isEditing, setIsEditing] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const fetchRequest = async () => {
      try {
        const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
        const response = await fetch(`${backendUrl}/requests/${requestId}`);
        if (!response.ok) throw new Error('Request not found');
        
        const data = await response.json();
        setRequest(data);
        if (data.results) {
          setLocalResults(data.results);
        }
      } catch (err) {
        console.error("Error fetching request:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchRequest();

    const channel = supabase.channel(`review-changes-${requestId}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'requests', filter: `request_id=eq.${requestId}` }, (payload) => {
        const freshRow = payload.new;
        if (!freshRow) return;
        
        setRequest(freshRow);
        if (freshRow.results) {
          // If we receive a backend update, override local state to stay synced
          setLocalResults(freshRow.results);
        }
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [requestId]);

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    
    try {
      const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
      const response = await fetch(`${backendUrl}/requests/${requestId}/corrections`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(localResults)
      });
      
      if (!response.ok) throw new Error('Failed to save');
      
      // Navigate immediately without the blocking alert
      navigate('/processed');
    } catch (err) {
      setSaveError(err.message);
      setSaving(false);
    }
  };

  const handleFlag = (index) => {
    setLocalResults(prev => prev.map((r, idx) => idx === index ? { ...r, status: 'flagged' } : r));
  };

  const handleUndo = (index) => {
    setLocalResults(prev => prev.map((r, idx) => idx === index ? { ...r, status: 'unreviewed', corrected_code: null } : r));
    setIsEditing(prev => ({...prev, [index]: false}));
  };

  const handleEditStart = (index) => {
    setIsEditing(prev => ({...prev, [index]: true}));
    setLocalResults(prev => prev.map((r, idx) => {
      if (idx === index && r.status === 'unreviewed') {
        return { ...r, status: 'flagged' };
      }
      return r;
    }));
  };

  const handleCorrectionChange = (index, value) => {
    // Atomic update: sets both corrected_code and status in the exact same state mutation
    setLocalResults(prev => prev.map((r, idx) => idx === index ? { ...r, corrected_code: value, status: 'corrected' } : r));
  };

  const handleCopyAll = () => {
    if (!localResults.length) return;
    
    const lines = localResults.map((res) => {
      const category = res.category.toUpperCase();
      const code = res.status === 'corrected' ? res.corrected_code : res.matched_code;
      return `${category}: ${res.concept}\nFinal Code: ${code}\n---`;
    });
    
    const textToCopy = lines.join('\n');
    
    navigator.clipboard.writeText(textToCopy).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const renderHighlightedText = () => {
    if (!request || !request.raw_input) return null;
    
    let text = request.raw_input;
    localResults.forEach(res => {
      const span = res.source_span;
      if (span && span.trim().length > 3) {
        text = text.replace(span, `<mark class="highlight">${span}</mark>`);
      }
    });
    
    return <div dangerouslySetInnerHTML={{ __html: text }} />;
  };

  if (loading) return <div className="page-container"><p>Loading request details...</p></div>;
  if (!request) return <div className="page-container"><p>Request not found.</p></div>;

  return (
    <div className="page-container" style={{ maxWidth: '1200px' }}>
      <Link to="/processed" className="back-link">
        <ArrowLeft size={15} />
        Back to Processed Records
      </Link>
      <h1 className="page-title">Code Review</h1>
      <p className="page-subtitle">Review and override the AI-suggested ICD-10 codes.</p>
      
      <div className="review-container">
        <div className="review-text-panel">
          <div className="form-group-title" style={{textAlign: 'left', marginBottom: '1.5rem'}}>Original Discharge Summary</div>
          {renderHighlightedText()}
        </div>
        
        <div className="review-codes-panel">
          {localResults.map((res, i) => {
            const isProcedure = (res.category || '').toLowerCase().startsWith('proc');
            
            // Badge style derived purely from status
            let statusBadge = null;
            if (res.status === 'flagged') {
              statusBadge = <span style={{ fontSize: '0.75rem', color: '#e11d48', fontWeight: '600', backgroundColor: '#ffe4e6', padding: '2px 6px', borderRadius: '4px' }}>Flagged Wrong</span>;
            } else if (res.status === 'corrected') {
              statusBadge = <span style={{ fontSize: '0.75rem', color: '#059669', fontWeight: '600', backgroundColor: '#d1fae5', padding: '2px 6px', borderRadius: '4px' }}>Manual Entry</span>;
            }

            return (
            <div key={i} className="code-card">
              <div className="code-card-header">
                <span className={`code-card-category ${isProcedure ? 'proc' : 'diag'}`}>
                  {isProcedure ? <Scissors size={13} /> : <Stethoscope size={13} />}
                  {res.category.toUpperCase()}: {res.concept}
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {statusBadge}
                  <span className={`mini-code-badge ${isProcedure ? 'proc' : 'diag'}`}>{res.matched_code}</span>
                </div>
              </div>
              
              <div className="code-card-span">
                "{res.source_span || 'N/A'}"
              </div>
              
              <div style={{fontSize: '0.9rem', marginBottom: '1rem'}}>
                <strong>AI Description:</strong> {res.matched_description}
              </div>
              
              <div className="correction-input">
                <label style={{fontSize: '0.85rem', fontWeight: 600}}>Final Code:</label>
                
                {isEditing[i] ? (
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <input 
                      type="text" 
                      value={res.corrected_code || ''} 
                      onChange={(e) => handleCorrectionChange(i, e.target.value)}
                      autoFocus
                    />
                    <button 
                      className="btn-secondary btn-small" 
                      style={{ padding: '0.3rem 0.5rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}
                      onClick={() => handleUndo(i)}
                      type="button"
                      title="Undo changes and close editor"
                    >
                      <Undo2 size={12} />
                      Undo
                    </button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ padding: '0.4rem 0.5rem', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '4px', minWidth: '100px' }}>
                      {res.status === 'corrected' ? res.corrected_code : res.matched_code}
                    </span>
                    
                    {res.status === 'unreviewed' && (
                      <button 
                        className="btn-secondary btn-small" 
                        style={{ padding: '0.3rem 0.5rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}
                        onClick={() => handleFlag(i)}
                        type="button"
                        title="Flag as wrong without providing a replacement yet"
                      >
                        <Flag size={12} />
                        Flag
                      </button>
                    )}
                    
                    <button 
                      className="btn-secondary btn-small" 
                      style={{ padding: '0.3rem 0.5rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}
                      onClick={() => handleEditStart(i)}
                      type="button"
                      title="Edit code"
                    >
                      <Edit2 size={12} />
                      Edit
                    </button>
                    
                    {(res.status === 'flagged' || res.status === 'corrected') && (
                      <button 
                        className="btn-secondary btn-small" 
                        style={{ padding: '0.3rem 0.5rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}
                        onClick={() => handleUndo(i)}
                        type="button"
                        title="Undo changes and revert to unreviewed"
                      >
                        <Undo2 size={12} />
                        Undo
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
            );
          })}
        </div>
      </div>
      
      {saveError && (
        <div style={{ marginTop: '1rem', padding: '0.75rem', backgroundColor: '#fee2e2', color: '#b91c1c', borderRadius: '4px', border: '1px solid #fecaca', fontSize: '0.9rem' }}>
          <strong>Error saving corrections:</strong> {saveError}
        </div>
      )}
      
      <div className="form-actions" style={{ marginTop: '1rem', display: 'flex', gap: '1rem' }}>
        <button className="btn-secondary" onClick={handleCopyAll} type="button">
          {copied ? <Check size={16} /> : <Copy size={16} />}
          {copied ? 'Copied!' : 'Copy All Codes'}
        </button>
        <button className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save & Submit Codes'}
        </button>
      </div>
    </div>
  );
}
