import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentList } from './DocumentList';
import { DocumentMetadata, api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    deleteDocument: vi.fn(),
  },
}));

describe('DocumentList Component', () => {
  const mockDocs: DocumentMetadata[] = [
    {
      document_id: 'doc-1',
      filename: 'resume.pdf',
      file_size_bytes: 1024 * 150, // 150 KB
      upload_timestamp: '2026-06-18T12:00:00Z',
      format: 'pdf',
      processing_status: 'completed',
    },
    {
      document_id: 'doc-2',
      filename: 'invoice.xlsx',
      file_size_bytes: 1024 * 1024 * 2.5, // 2.5 MB
      upload_timestamp: '2026-06-18T13:00:00Z',
      format: 'xlsx',
      processing_status: 'processing',
    },
  ];

  const mockOnDeleteSuccess = vi.fn();
  const mockAddToast = vi.fn();
  const mockSetCurrentPage = vi.fn();
  const mockSetItemsPerPage = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('confirm', vi.fn(() => true));
  });

  it('renders empty state message when no documents exist', () => {
    render(
      <DocumentList
        documents={[]}
        onDeleteSuccess={mockOnDeleteSuccess}
        addToast={mockAddToast}
        currentPage={1}
        setCurrentPage={mockSetCurrentPage}
        itemsPerPage={10}
        setItemsPerPage={mockSetItemsPerPage}
      />
    );
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText(/No documents uploaded yet/i)).toBeInTheDocument();
  });

  it('renders document items with sizes, formats, timestamps, and badges', () => {
    render(
      <DocumentList
        documents={mockDocs}
        onDeleteSuccess={mockOnDeleteSuccess}
        addToast={mockAddToast}
        currentPage={1}
        setCurrentPage={mockSetCurrentPage}
        itemsPerPage={10}
        setItemsPerPage={mockSetItemsPerPage}
      />
    );

    expect(screen.getByText('resume.pdf')).toBeInTheDocument();
    expect(screen.getByText('150 KB')).toBeInTheDocument();
    expect(screen.getByTestId('status-completed')).toHaveTextContent('completed');

    expect(screen.getByText('invoice.xlsx')).toBeInTheDocument();
    expect(screen.getByText('2.5 MB')).toBeInTheDocument();
    expect(screen.getByTestId('status-processing')).toHaveTextContent('processing');
  });

  it('triggers delete flow when delete button is clicked and confirmed', async () => {
    vi.mocked(api.deleteDocument).mockResolvedValueOnce({ status: 'deleted', document_id: 'doc-1' });

    render(
      <DocumentList
        documents={mockDocs}
        onDeleteSuccess={mockOnDeleteSuccess}
        addToast={mockAddToast}
        currentPage={1}
        setCurrentPage={mockSetCurrentPage}
        itemsPerPage={10}
        setItemsPerPage={mockSetItemsPerPage}
      />
    );

    const deleteButtons = screen.getAllByTestId('delete-btn');
    fireEvent.click(deleteButtons[0]);

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('resume.pdf'));
    
    await waitFor(() => {
      expect(api.deleteDocument).toHaveBeenCalledWith('doc-1');
    });

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('success', expect.stringContaining('deleted successfully'));
      expect(mockOnDeleteSuccess).toHaveBeenCalled();
    });
  });

  it('paginates documents list correctly', () => {
    // Generate 12 docs
    const manyDocs = Array.from({ length: 12 }, (_, i) => ({
      document_id: `doc-${i}`,
      filename: `doc-${i}.txt`,
      file_size_bytes: 100,
      upload_timestamp: new Date().toISOString(),
      format: 'txt' as const,
      processing_status: 'completed' as const,
    }));

    render(
      <DocumentList
        documents={manyDocs}
        onDeleteSuccess={mockOnDeleteSuccess}
        addToast={mockAddToast}
        currentPage={1}
        setCurrentPage={mockSetCurrentPage}
        itemsPerPage={10}
        setItemsPerPage={mockSetItemsPerPage}
      />
    );

    // Page 1 should list 10 documents
    const docItems = screen.getAllByTestId('document-item');
    expect(docItems).toHaveLength(10);
    expect(screen.getByText('doc-0.txt')).toBeInTheDocument();
    expect(screen.queryByText('doc-10.txt')).not.toBeInTheDocument();

    const nextPageBtn = screen.getByTestId('next-page-btn');
    fireEvent.click(nextPageBtn);
    expect(mockSetCurrentPage).toHaveBeenCalledWith(2);
  });
});
