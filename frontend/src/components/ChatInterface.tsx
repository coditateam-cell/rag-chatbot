import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, ChevronDown, Plus, Loader2 } from 'lucide-react';
import type { ChatMessage, RankedChunk, DocumentMetadata } from '../api/client';
import { api } from '../api/client';

interface ChatInterfaceProps {
  sessionId: string | null;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  addToast: (type: 'success' | 'error', message: string) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  onUploadSuccess?: (docId: string) => void;
  activeDocumentIds: string[];
  documents: DocumentMetadata[];
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  sessionId,
  messages,
  setMessages,
  addToast,
  isLoading,
  setIsLoading,
  onUploadSuccess,
  activeDocumentIds,
  documents,
}) => {
  const [query, setQuery] = useState('');
  const historyEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isUploadingFiles, setIsUploadingFiles] = useState(false);

  useEffect(() => {
    if (sessionId && textareaRef.current && !isLoading) {
      textareaRef.current.focus();
    }
  }, [sessionId, isLoading]);

  const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.xlsx', '.xls', '.txt', '.png', '.jpg', '.jpeg'];
  const MAX_FILE_SIZE = 10 * 1024 * 1024;

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const files = Array.from(e.target.files);
    setIsUploadingFiles(true);
    let successCount = 0;
    
    for (const file of files) {
      const extension = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!ALLOWED_EXTENSIONS.includes(extension || '')) {
        addToast('error', `Unsupported format: ${file.name}`);
        continue;
      }
      if (file.size > MAX_FILE_SIZE) {
        addToast('error', `${file.name} exceeds 10MB limit`);
        continue;
      }
      if (file.size === 0) {
        addToast('error', `${file.name} is empty`);
        continue;
      }
      
      try {
        const response = await api.uploadDocument(file);
        successCount++;
        if (onUploadSuccess) onUploadSuccess(response.document_id);
      } catch (err: any) {
        addToast('error', `Failed to upload ${file.name}: ${err.detail || 'Unknown error'}`);
      }
    }
    
    setIsUploadingFiles(false);
    if (e.target) e.target.value = '';
    if (successCount > 0) {
      addToast('success', `Uploaded ${successCount} document(s). Processing in background...`);
    }
  };

  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionId || !query.trim() || isLoading) return;

    const userText = query.trim();

    // Add user message locally
    const userMsg: ChatMessage = {
      message_id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(),
      session_id: sessionId,
      role: 'user',
      content: userText,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setQuery('');
    setIsLoading(true);

    try {
      const response = await api.queryChat(sessionId, userText, activeDocumentIds);
      
      const assistantMsg: ChatMessage = {
        message_id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(),
        session_id: sessionId,
        role: 'assistant',
        content: response.answer,
        timestamp: response.response_timestamp,
        query_text: userText,
        retrieved_chunk_ids: response.retrieved_chunks.map((rc) => rc.chunk.chunk_id),
        reranking_scores: response.reranking_scores,
        reranking_provider: response.reranking_provider,
        reranking_duration_ms: response.reranking_duration_ms,
      };

      // We attach the retrieved chunks inline as metadata so we can display them inside this message
      (assistantMsg as any).retrieved_chunks = response.retrieved_chunks;

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const detail = err.detail || 'Failed to retrieve response from LLM.';
      addToast('error', `Chat error: ${detail}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(e);
    }
  };



  return (
    <div className="chat-container">
      {/* Active Context Bar */}
      <div className="active-docs-bar" style={{
        padding: '10px 16px',
        borderBottom: '1px solid hsl(var(--border))',
        background: 'hsl(var(--bg-secondary) / 0.3)',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '0.8rem',
        color: 'hsl(var(--text-secondary))'
      }}>
        <span style={{ fontWeight: 600 }}>Active Context:</span>
        {activeDocumentIds.length === 0 ? (
          <span style={{ fontStyle: 'italic', color: 'hsl(var(--text-muted))' }}>No documents selected (General Chat Mode)</span>
        ) : (
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {documents
              .filter(doc => activeDocumentIds.includes(doc.document_id))
              .map(doc => (
                <span key={doc.document_id} className="badge" style={{
                  background: 'hsl(var(--accent-primary) / 0.15)',
                  color: 'hsl(var(--accent-secondary))',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  fontSize: '0.7rem',
                  border: '1px solid hsl(var(--accent-primary) / 0.3)'
                }}>
                  {doc.filename}
                </span>
              ))
            }
          </div>
        )}
      </div>

      <div className="chat-history" data-testid="chat-history">
        {messages.length === 0 ? (
          <div className="empty-state">
            <Sparkles className="empty-state-icon" size={36} />
            <h2 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Chat with Knowledge Base</h2>
            <p style={{ fontSize: '0.85rem', color: 'hsl(var(--text-secondary))', maxWidth: '460px' }}>
              Ask questions grounded in your uploaded documents. The AI will retrieve relevant sections and cite its sources.
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.message_id}
              className={`chat-message-row ${msg.role}`}
              data-testid={`message-${msg.role}`}
            >
              <div className="chat-bubble">
                <div>{msg.content}</div>
                {msg.role === 'assistant' && (msg as any).retrieved_chunks && (msg as any).retrieved_chunks.length > 0 && (
                  <SourcesAccordion chunks={(msg as any).retrieved_chunks} />
                )}
                <span className="message-time">
                  {new Date(msg.timestamp).toLocaleTimeString(undefined, {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="typing-loader" data-testid="typing-loader" style={{ alignSelf: 'flex-start' }}>
            <div className="typing-dot"></div>
            <div className="typing-dot"></div>
            <div className="typing-dot"></div>
          </div>
        )}
        <div ref={historyEndRef} />
      </div>

      <div className="chat-input-container">
        <form onSubmit={handleSend}>
          <div className="chat-input-wrapper">
            <textarea
              ref={textareaRef}
              className="chat-textarea"
              placeholder={sessionId ? "Ask a question about your documents..." : "Initializing chat session..."}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!sessionId || isLoading}
              rows={1}
              data-testid="chat-input"
            />
            <div className="chat-input-actions">
              <input
                type="file"
                multiple
                ref={fileInputRef}
                style={{ display: 'none' }}
                onChange={handleFileUpload}
                accept=".pdf,.docx,.pptx,.xlsx,.xls,.txt,.png,.jpg,.jpeg"
              />
              <button
                type="button"
                className="add-doc-btn"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploadingFiles}
                title="Add multiple documents"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'hsl(var(--text-secondary))',
                  cursor: isUploadingFiles ? 'not-allowed' : 'pointer',
                  padding: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: '50%',
                  transition: 'background-color 0.2s',
                }}
                onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'hsl(var(--bg-tertiary))'}
                onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                {isUploadingFiles ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
              </button>
              <button
                type="submit"
                className="send-btn"
                disabled={!sessionId || !query.trim() || isLoading}
                aria-label="Send message"
                data-testid="send-btn"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};

const SourcesAccordion: React.FC<{ chunks: RankedChunk[] }> = ({ chunks }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="sources-accordion" data-testid="sources-accordion">
      <div className="sources-toggle" onClick={() => setIsOpen(!isOpen)} data-testid="sources-toggle">
        <span>Cited Sources ({chunks.length})</span>
        {isOpen ? <ChevronDown size={12} style={{ transform: 'rotate(180deg)' }} /> : <ChevronDown size={12} />}
      </div>
      {isOpen && (
        <div className="sources-content" data-testid="sources-content">
          {chunks.map((rc, idx) => (
            <div key={rc.chunk.chunk_id || idx} className="source-item" data-testid="source-item">
              <div className="source-item-header">
                <span>Chunk #{rc.chunk.position_in_document + 1}</span>
                <span>Score: {rc.score.toFixed(3)}</span>
              </div>
              {rc.chunk.contextual_summary && (
                <div style={{ fontStyle: 'italic', marginBottom: '4px', opacity: 0.8 }}>
                  Summary: {rc.chunk.contextual_summary}
                </div>
              )}
              <div className="source-text">{rc.chunk.chunk_text}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
