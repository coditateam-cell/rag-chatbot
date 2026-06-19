import React, { useState } from 'react';
import { Trash2, FileText, ChevronLeft, ChevronRight, File } from 'lucide-react';
import type { DocumentMetadata } from '../api/client';
import { api } from '../api/client';

interface DocumentListProps {
  documents: DocumentMetadata[];
  onDeleteSuccess: () => void;
  addToast: (type: 'success' | 'error', message: string) => void;
  currentPage: number;
  setCurrentPage: (page: number) => void;
  itemsPerPage: number;
  setItemsPerPage: (items: number) => void;
  onChatWithDoc?: (docId: string) => void;
}

export const DocumentList: React.FC<DocumentListProps> = ({
  documents,
  onDeleteSuccess,
  addToast,
  currentPage,
  setCurrentPage,
  itemsPerPage,
  setItemsPerPage,
  onChatWithDoc,
}) => {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"?`)) return;
    setDeletingId(docId);
    try {
      await api.deleteDocument(docId);
      addToast('success', `"${filename}" deleted successfully.`);
      onDeleteSuccess();
    } catch (err: any) {
      const detail = err.detail || 'Could not delete document.';
      addToast('error', `Delete failed: ${detail}`);
    } finally {
      setDeletingId(null);
    }
  };

  const paginatedDocs = documents.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );
  
  const totalPages = Math.max(1, Math.ceil(documents.length / itemsPerPage));

  const handlePrevPage = () => {
    if (currentPage > 1) setCurrentPage(currentPage - 1);
  };

  const handleNextPage = () => {
    if (currentPage < totalPages) setCurrentPage(currentPage + 1);
  };

  return (
    <div className="doc-list-container">
      <div className="doc-list-header">
        <h3 style={{ fontSize: '0.95rem' }}>Managed Knowledge Base</h3>
        <select
          value={itemsPerPage}
          onChange={(e) => {
            setItemsPerPage(Number(e.target.value));
            setCurrentPage(1);
          }}
          style={{
            background: 'hsl(var(--bg-tertiary))',
            color: 'hsl(var(--text-primary))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '4px',
            padding: '2px 4px',
            fontSize: '0.75rem',
            cursor: 'pointer',
          }}
          data-testid="page-size-select"
        >
          <option value={10}>10 / page</option>
          <option value={25}>25 / page</option>
          <option value={50}>50 / page</option>
          <option value={100}>100 / page</option>
        </select>
      </div>

      <div className="doc-items">
        {documents.length === 0 ? (
          <div className="empty-state" data-testid="empty-state">
            <File className="empty-state-icon" size={32} />
            <p style={{ fontSize: '0.8rem', fontWeight: 500 }}>No documents uploaded yet.</p>
            <p style={{ fontSize: '0.7rem', color: 'hsl(var(--text-muted))', marginTop: '4px' }}>
              Your knowledge base is empty. Upload a supported file above to get started.
            </p>
          </div>
        ) : (
          paginatedDocs.map((doc) => (
            <div key={doc.document_id} className="doc-card" data-testid="document-item">
              <div className="doc-card-row">
                <div 
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, cursor: onChatWithDoc && doc.processing_status === 'completed' ? 'pointer' : 'default' }}
                  onClick={() => {
                     if (onChatWithDoc && doc.processing_status === 'completed') {
                         onChatWithDoc(doc.document_id);
                     }
                  }}
                >
                  <FileText size={16} style={{ color: 'hsl(var(--accent-secondary))', flexShrink: 0 }} />
                  <span className="doc-name" title={doc.filename} style={{ color: onChatWithDoc && doc.processing_status === 'completed' ? 'hsl(var(--accent-primary))' : 'inherit', transition: 'color 0.2s' }}>{doc.filename}</span>
                </div>
                <button
                  onClick={() => handleDelete(doc.document_id, doc.filename)}
                  className="btn btn-secondary"
                  style={{ padding: '6px', minHeight: 'unset', border: 'none', background: 'transparent' }}
                  disabled={deletingId === doc.document_id}
                  aria-label="Delete document"
                  data-testid="delete-btn"
                >
                  <Trash2 size={14} style={{ color: 'hsl(var(--error))' }} />
                </button>
              </div>
              <div className="doc-card-row" style={{ marginTop: '8px' }}>
                <div className="doc-meta">
                  <span>{formatBytes(doc.file_size_bytes)}</span>
                  <span>•</span>
                  <span>{formatDate(doc.upload_timestamp)}</span>
                </div>
                <span className={`badge badge-${doc.processing_status}`} data-testid={`status-${doc.processing_status}`}>
                  {doc.processing_status}
                </span>
              </div>
              {doc.error_detail && (
                <div style={{ fontSize: '0.7rem', color: 'hsl(var(--error))', marginTop: '6px', wordBreak: 'break-word' }}>
                  Err: {doc.error_detail}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {documents.length > 0 && (
        <div className="pagination-controls" data-testid="pagination">
          <span>
            Page {currentPage} of {totalPages} ({documents.length} total)
          </span>
          <div className="pagination-buttons">
            <button
              onClick={handlePrevPage}
              disabled={currentPage === 1}
              className="pagination-btn"
              data-testid="prev-page-btn"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={handleNextPage}
              disabled={currentPage === totalPages}
              className="pagination-btn"
              data-testid="next-page-btn"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
