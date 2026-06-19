import { useState, useEffect } from 'react';
import { Bot, RefreshCw, Settings2, ArrowRight } from 'lucide-react';
import { UploadForm } from './components/UploadForm';
import { DocumentList } from './components/DocumentList';
import { ChatInterface } from './components/ChatInterface';
import { Notification } from './components/Notification';
import type { ToastMessage } from './components/Notification';
import type { DocumentMetadata, ChatMessage } from './api/client';
import { api } from './api/client';

function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isConfigReloading, setIsConfigReloading] = useState(false);
  // View State: 'upload' or 'chat'
  const [currentView, setCurrentView] = useState<'upload' | 'chat'>(
    window.location.hash === '#chat' ? 'chat' : 'upload'
  );

  const [activeDocumentIds, setActiveDocumentIds] = useState<string[]>([]);
  const [pendingDocumentIds, setPendingDocumentIds] = useState<string[]>([]);

  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '');
      if (hash === 'chat' || hash === 'upload') {
        setCurrentView(hash);
      } else if (!hash) {
        setCurrentView('upload');
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    if (window.location.hash.replace('#', '') !== currentView) {
      window.location.hash = currentView;
    }
  }, [currentView]);

  
  const addToast = (type: 'success' | 'error', message: string) => {
    const id = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString());
    setToasts((prev) => [...prev, { id, type, message }]);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const startNewChat = async () => {
    setMessages([]);
    setActiveDocumentIds([]);
    try {
      const response = await api.createSession();
      setSessionId(response.session_id);
    } catch (err: any) {
      addToast('error', `Failed to initialize chat session: ${err.detail || 'Server offline'}`);
    }
  };

  const initSession = async () => {
    try {
      const response = await api.createSession();
      setSessionId(response.session_id);
    } catch (err: any) {
      addToast('error', `Failed to initialize chat session: ${err.detail || 'Server offline'}`);
    }
  };

  const fetchDocuments = async () => {
    try {
      const docs = await api.listDocuments(200, 0, sessionId || undefined);
      setDocuments(docs);
    } catch (err: any) {
      addToast('error', `Failed to fetch documents: ${err.detail || 'Connection failure'}`);
    }
  };

  useEffect(() => {
    initSession();
  }, []);

  useEffect(() => {
    if (sessionId) {
      fetchDocuments();
      api.getChatHistory(sessionId)
        .then(history => {
          setMessages(history);
        })
        .catch(err => {
          console.error("Failed to fetch chat history:", err);
        });
    }
  }, [sessionId]);

  useEffect(() => {
    if (pendingDocumentIds.length > 0) {
      const finishedDocs = documents.filter(
        doc => pendingDocumentIds.includes(doc.document_id) &&
               (doc.processing_status === 'completed' || doc.processing_status === 'failed')
      );

      if (finishedDocs.length > 0) {
        const finishedIds = finishedDocs.map(d => d.document_id);
        setPendingDocumentIds(prev => prev.filter(id => !finishedIds.includes(id)));

        const completedIds = finishedDocs
          .filter(d => d.processing_status === 'completed')
          .map(d => d.document_id);

        if (completedIds.length > 0) {
          setActiveDocumentIds(prev => {
            if (currentView !== 'chat') {
              return completedIds;
            } else {
              const next = [...prev];
              completedIds.forEach(id => {
                if (!next.includes(id)) next.push(id);
              });
              return next;
            }
          });

          if (currentView !== 'chat') {
            setCurrentView('chat');
          }
          addToast('success', `${completedIds.length} document(s) successfully embedded and ready for chat!`);
        }

        const failedDocs = finishedDocs.filter(d => d.processing_status === 'failed');
        if (failedDocs.length > 0) {
          addToast('error', `${failedDocs.length} document(s) failed embedding.`);
        }
      }
    }

    const hasActiveProcessing = documents.some(
      (doc) => doc.processing_status === 'pending' || doc.processing_status === 'processing'
    );
    if (!hasActiveProcessing && pendingDocumentIds.length === 0) return;
    const interval = setInterval(() => {
      fetchDocuments();
    }, 3000);
    return () => clearInterval(interval);
  }, [documents, pendingDocumentIds, currentView]);

  const handleConfigReload = async () => {
    setIsConfigReloading(true);
    try {
      await api.reloadConfig();
      addToast('success', 'Configuration reloaded successfully.');
    } catch (err: any) {
      addToast('error', `Hot-reload failed: ${err.detail || 'Unknown error'}`);
    } finally {
      setIsConfigReloading(false);
    }
  };

  const handleUploadSuccess = (docId: string) => {
    setPendingDocumentIds(prev => [...prev, docId]);
    fetchDocuments();
  };

  const handleChatWithDoc = async (docId: string) => {
    await startNewChat();
    setActiveDocumentIds([docId]);
    setCurrentView('chat');
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }} onClick={() => {
          setCurrentView('upload');
          startNewChat();
        }}>
          <Bot size={28} style={{ color: 'hsl(var(--accent-primary))' }} />
          <h1 style={{ fontSize: '1.25rem' }} className="text-gradient">
            RAG Chatbot Workspace
          </h1>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {currentView === 'upload' && documents.length > 0 && (
            <button
              onClick={() => setCurrentView('chat')}
              className="btn btn-primary pulse-animation"
              style={{ padding: '8px 16px', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              Start Chatting <ArrowRight size={16} />
            </button>
          )}

          <button
            onClick={handleConfigReload}
            disabled={isConfigReloading}
            className="btn btn-secondary"
            style={{ padding: '8px 12px', fontSize: '0.8rem' }}
            title="Hot-reload server configurations"
          >
            <RefreshCw size={14} className={isConfigReloading ? 'animate-spin' : ''} />
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }} className="hide-on-mobile">
              <Settings2 size={12} /> Reload Config
            </span>
          </button>
          
          {sessionId && (
            <span style={{ fontSize: '0.75rem', color: 'hsl(var(--text-muted))' }} className="hide-on-mobile">
              Session: {sessionId.substring(0, 8)}...
            </span>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="app-main" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {currentView === 'upload' ? (
          <div className="upload-view-container animate-fade-in" style={{ flex: 1, overflowY: 'auto', padding: '2rem' }}>
            <div className="upload-view-content" style={{ maxWidth: '800px', margin: '0 auto' }}>
              <div className="hero-section text-center" style={{ marginBottom: '2rem' }}>
                 <h2 className="text-gradient" style={{ fontSize: '2.5rem', fontWeight: 'bold', marginBottom: '1rem' }}>Feed Your Knowledge Base</h2>
                 <p style={{ color: 'hsl(var(--text-muted))', fontSize: '1.1rem' }}>Upload documents to give your AI assistant context. Once uploaded, you can start chatting instantly.</p>
              </div>
              
              <div className="glass-panel" style={{ padding: '2rem', borderRadius: '12px', marginBottom: '2rem', position: 'relative' }}>
                {pendingDocumentIds.length > 0 && (
                  <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.7)', borderRadius: '12px', zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                    <RefreshCw size={40} className="animate-spin text-gradient-accent" style={{ marginBottom: '16px' }} />
                    <h3 style={{ color: 'white', fontSize: '1.2rem', fontWeight: 600 }}>Embedding Document(s)...</h3>
                    <p style={{ color: 'hsl(var(--text-muted))', marginTop: '8px' }}>Please wait while your document is being processed.</p>
                  </div>
                )}
                <UploadForm onUploadSuccess={handleUploadSuccess} addToast={addToast} sessionId={sessionId} />
              </div>
              
              {documents.length > 0 && (
                <div className="glass-panel animate-slide-up" style={{ padding: '2rem', borderRadius: '12px', marginTop: '2rem' }}>
                  <h3 style={{ marginBottom: '1rem', color: 'hsl(var(--text-primary))', fontSize: '1.2rem', fontWeight: 600 }}>Your Document Library</h3>
                  <DocumentList
                    documents={documents}
                    onDeleteSuccess={fetchDocuments}
                    addToast={addToast}
                    currentPage={currentPage}
                    setCurrentPage={setCurrentPage}
                    itemsPerPage={itemsPerPage}
                    setItemsPerPage={setItemsPerPage}
                    onChatWithDoc={handleChatWithDoc}
                  />
                </div>
              )}
            </div>
          </div>
        ) : (
          <section className="app-workspace chat-view-container animate-fade-in" style={{ flex: 1, width: '100%', height: '100%', display: 'flex', flexDirection: 'column', maxWidth: '1000px', margin: '0 auto', padding: '1rem' }}>
             <div className="glass-panel" style={{ flex: 1, borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
               <ChatInterface
                  sessionId={sessionId}
                  messages={messages}
                  setMessages={setMessages}
                  addToast={addToast}
                  isLoading={isChatLoading}
                  setIsLoading={setIsChatLoading}
                  onUploadSuccess={handleUploadSuccess}
                  activeDocumentIds={activeDocumentIds}
                  documents={documents}
               />
             </div>
          </section>
        )}
      </main>

      <Notification toasts={toasts} onClose={removeToast} />
    </div>
  );
}

export default App;
