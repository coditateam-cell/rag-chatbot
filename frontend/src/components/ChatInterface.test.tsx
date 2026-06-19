import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatInterface } from './ChatInterface';
import { ChatMessage, api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    queryChat: vi.fn(),
  },
}));

describe('ChatInterface Component', () => {
  const mockMessages: ChatMessage[] = [
    {
      message_id: 'msg-1',
      session_id: 'sess-1',
      role: 'user',
      content: 'What is deep learning?',
      timestamp: '2026-06-18T14:00:00Z',
    },
    {
      message_id: 'msg-2',
      session_id: 'sess-1',
      role: 'assistant',
      content: 'Deep learning is a subset of machine learning...',
      timestamp: '2026-06-18T14:01:00Z',
    },
  ];

  const mockSetMessages = vi.fn();
  const mockAddToast = vi.fn();
  const mockSetIsLoading = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders instructions in empty state', () => {
    render(
      <ChatInterface
        sessionId="sess-1"
        messages={[]}
        setMessages={mockSetMessages}
        addToast={mockAddToast}
        isLoading={false}
        setIsLoading={mockSetIsLoading}
      />
    );
    expect(screen.getByText(/Chat with Knowledge Base/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Ask a question about your documents.../i)).toBeInTheDocument();
  });

  it('renders chat message bubbles', () => {
    render(
      <ChatInterface
        sessionId="sess-1"
        messages={mockMessages}
        setMessages={mockSetMessages}
        addToast={mockAddToast}
        isLoading={false}
        setIsLoading={mockSetIsLoading}
      />
    );
    expect(screen.getByText('What is deep learning?')).toBeInTheDocument();
    expect(screen.getByText('Deep learning is a subset of machine learning...')).toBeInTheDocument();
  });

  it('updates remaining character counter as user types', () => {
    render(
      <ChatInterface
        sessionId="sess-1"
        messages={[]}
        setMessages={mockSetMessages}
        addToast={mockAddToast}
        isLoading={false}
        setIsLoading={mockSetIsLoading}
      />
    );

    const input = screen.getByPlaceholderText(/Ask a question about your documents.../i);
    fireEvent.change(input, { target: { value: 'Hello' } });

    expect(screen.getByTestId('char-counter')).toHaveTextContent('5/2000');
  });

  it('shows typing loader when isLoading is true', () => {
    render(
      <ChatInterface
        sessionId="sess-1"
        messages={mockMessages}
        setMessages={mockSetMessages}
        addToast={mockAddToast}
        isLoading={true}
        setIsLoading={mockSetIsLoading}
      />
    );
    expect(screen.getByTestId('typing-loader')).toBeInTheDocument();
  });

  it('renders citations accordion if retrieved chunks exist', () => {
    const assistantMsgWithCitations: any = {
      message_id: 'msg-3',
      session_id: 'sess-1',
      role: 'assistant',
      content: 'According to document...',
      timestamp: '2026-06-18T14:02:00Z',
      retrieved_chunks: [
        {
          chunk: {
            chunk_id: 'chunk-1',
            document_id: 'doc-1',
            chunk_text: 'Deep learning is inspired by the human brain.',
            position_in_document: 0,
            contextual_summary: 'Brain inspiration explanation.',
          },
          score: 0.952,
        },
      ],
    };

    render(
      <ChatInterface
        sessionId="sess-1"
        messages={[assistantMsgWithCitations]}
        setMessages={mockSetMessages}
        addToast={mockAddToast}
        isLoading={false}
        setIsLoading={mockSetIsLoading}
      />
    );

    const citationsToggle = screen.getByTestId('sources-toggle');
    expect(citationsToggle).toHaveTextContent('Cited Sources (1)');

    // Toggle sources to expand
    fireEvent.click(citationsToggle);

    expect(screen.getByText('Deep learning is inspired by the human brain.')).toBeInTheDocument();
    expect(screen.getByText('Summary: Brain inspiration explanation.')).toBeInTheDocument();
    expect(screen.getByText('Score: 0.952')).toBeInTheDocument();
  });
});
