import React, { useState, useRef } from 'react';
import { UploadCloud, FileText } from 'lucide-react';
import { api } from '../api/client';

interface UploadFormProps {
  onUploadSuccess: (docId: string) => void;
  addToast: (type: 'success' | 'error', message: string) => void;
}

const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.xlsx', '.xls', '.txt', '.png', '.jpg', '.jpeg'];
const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500 MB

export const UploadForm: React.FC<UploadFormProps> = ({ onUploadSuccess, addToast }) => {
  const [isDragActive, setIsDragActive] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): boolean => {
    const extension = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      addToast('error', `Unsupported file format. Supported extensions: ${ALLOWED_EXTENSIONS.join(', ')}`);
      return false;
    }
    if (file.size > MAX_FILE_SIZE) {
      addToast('error', 'File exceeds the 500 MB size limit.');
      return false;
    }
    if (file.size === 0) {
      addToast('error', 'Empty files are not allowed.');
      return false;
    }
    return true;
  };

  const handleUpload = async (file: File) => {
    if (!validateFile(file)) return;

    setIsUploading(true);
    setUploadProgress(0);

    try {
      const response = await api.uploadDocument(file, (progress) => {
        setUploadProgress(progress);
      });
      addToast('success', `"${file.name}" uploaded successfully! Chunk processing started.`);
      onUploadSuccess(response.document_id);
    } catch (err: any) {
      const detail = err.detail || 'Connection failure to server.';
      addToast('error', `Upload failed: ${detail}`);
    } finally {
      setIsUploading(false);
      setUploadProgress(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragActive(true);
    } else if (e.type === 'dragleave') {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleUpload(e.target.files[0]);
    }
  };

  return (
    <div className="upload-container">
      <h3 style={{ marginBottom: '12px', fontSize: '0.95rem' }}>Upload Context Document</h3>
      <div
        className={`dropzone ${isDragActive ? 'active' : ''}`}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        data-testid="dropzone"
      >
        <input
          ref={fileInputRef}
          type="file"
          style={{ display: 'none' }}
          onChange={handleFileChange}
          disabled={isUploading}
          accept={ALLOWED_EXTENSIONS.join(',')}
          data-testid="file-input"
        />
        {isUploading ? (
          <>
            <FileText className="dropzone-icon" size={32} />
            <div style={{ fontSize: '0.85rem', fontWeight: 500 }}>Uploading Document...</div>
            <div className="progress-container">
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'hsl(var(--text-secondary))' }}>
                <span>Progress</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="progress-bar-bg">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${uploadProgress}%` }}
                  data-testid="progress-bar"
                ></div>
              </div>
            </div>
          </>
        ) : (
          <>
            <UploadCloud className="dropzone-icon" size={32} />
            <div style={{ fontSize: '0.85rem', fontWeight: 500 }}>
              Drag & Drop file here or <span className="text-gradient-accent">browse</span>
            </div>
            <div style={{ fontSize: '0.7rem', color: 'hsl(var(--text-muted))' }}>
              PDF, DOCX, PPTX, XLS, TXT, PNG, JPG (max 500MB)
            </div>
          </>
        )}
      </div>
    </div>
  );
};
