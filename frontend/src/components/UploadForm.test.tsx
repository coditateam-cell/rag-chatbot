import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { UploadForm } from './UploadForm';
import { api } from '../api/client';

// Mock API client
vi.mock('../api/client', () => ({
  api: {
    uploadDocument: vi.fn(),
  },
}));

describe('UploadForm Component', () => {
  const mockOnUploadSuccess = vi.fn();
  const mockAddToast = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders instructions and dropzone correctly', () => {
    render(<UploadForm onUploadSuccess={mockOnUploadSuccess} addToast={mockAddToast} />);
    expect(screen.getByText(/Drag & Drop file here/i)).toBeInTheDocument();
    expect(screen.getByText(/PDF, DOCX, PPTX, XLS, TXT, PNG, JPG/i)).toBeInTheDocument();
  });

  it('rejects files larger than 10MB', async () => {
    render(<UploadForm onUploadSuccess={mockOnUploadSuccess} addToast={mockAddToast} />);
    const file = new File(['a'.repeat(11 * 1024 * 1024)], 'large.pdf', { type: 'application/pdf' });
    
    const input = screen.getByTestId('file-input');
    fireEvent.change(input, { target: { files: [file] } });

    expect(mockAddToast).toHaveBeenCalledWith('error', 'File exceeds the 10 MB size limit.');
    expect(api.uploadDocument).not.toHaveBeenCalled();
  });

  it('rejects empty files', async () => {
    render(<UploadForm onUploadSuccess={mockOnUploadSuccess} addToast={mockAddToast} />);
    const file = new File([], 'empty.txt', { type: 'text/plain' });
    
    const input = screen.getByTestId('file-input');
    fireEvent.change(input, { target: { files: [file] } });

    expect(mockAddToast).toHaveBeenCalledWith('error', 'Empty files are not allowed.');
    expect(api.uploadDocument).not.toHaveBeenCalled();
  });

  it('rejects unsupported file extensions', async () => {
    render(<UploadForm onUploadSuccess={mockOnUploadSuccess} addToast={mockAddToast} />);
    const file = new File(['content'], 'document.exe', { type: 'application/octet-stream' });
    
    const input = screen.getByTestId('file-input');
    fireEvent.change(input, { target: { files: [file] } });

    expect(mockAddToast).toHaveBeenCalledWith('error', expect.stringContaining('Unsupported file format'));
    expect(api.uploadDocument).not.toHaveBeenCalled();
  });

  it('accepts and uploads a valid document and triggers callbacks', async () => {
    vi.mocked(api.uploadDocument).mockResolvedValueOnce({
      document_id: 'test-uuid-1234',
      upload_timestamp: new Date().toISOString(),
    });

    render(<UploadForm onUploadSuccess={mockOnUploadSuccess} addToast={mockAddToast} />);
    const file = new File(['%PDF-1.4\ntest'], 'valid.pdf', { type: 'application/pdf' });
    
    const input = screen.getByTestId('file-input');
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByText(/Uploading Document.../i)).toBeInTheDocument();

    await waitFor(() => {
      expect(api.uploadDocument).toHaveBeenCalledWith(file, expect.any(Function));
    });

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('success', expect.stringContaining('uploaded successfully'));
      expect(mockOnUploadSuccess).toHaveBeenCalledWith('test-uuid-1234');
    });
  });
});
