import React, { useEffect } from 'react';
import { CheckCircle2, AlertCircle, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error';
  message: string;
}

interface NotificationProps {
  toasts: ToastMessage[];
  onClose: (id: string) => void;
}

export const Notification: React.FC<NotificationProps> = ({ toasts, onClose }) => {
  return (
    <div className="toast-container" data-testid="toast-container">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onClose={onClose} />
      ))}
    </div>
  );
};

const ToastItem: React.FC<{ toast: ToastMessage; onClose: (id: string) => void }> = ({
  toast,
  onClose,
}) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose(toast.id);
    }, 5000);
    return () => clearTimeout(timer);
  }, [toast.id, onClose]);

  return (
    <div className={`toast toast-${toast.type}`} data-testid={`toast-${toast.type}`}>
      {toast.type === 'success' ? (
        <CheckCircle2 size={18} className="toast-icon" />
      ) : (
        <AlertCircle size={18} className="toast-icon" />
      )}
      <div style={{ flex: 1, wordBreak: 'break-word' }}>{toast.message}</div>
      <button
        onClick={() => onClose(toast.id)}
        style={{
          background: 'none',
          border: 'none',
          color: 'currentColor',
          cursor: 'pointer',
          display: 'flex',
          padding: 0,
        }}
        aria-label="Close notification"
      >
        <X size={16} />
      </button>
    </div>
  );
};
