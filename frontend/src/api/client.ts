// API Client for RAG Chatbot Application

export type ProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed';

export type DocumentFormat =
  | 'pdf'
  | 'docx'
  | 'pptx'
  | 'xlsx'
  | 'xls'
  | 'txt'
  | 'png'
  | 'jpg'
  | 'jpeg';

export interface DocumentMetadata {
  document_id: string;
  filename: string;
  upload_timestamp: string;
  file_size_bytes: number;
  format: DocumentFormat;
  processing_status: ProcessingStatus;
  error_detail?: string | null;
}

export interface Chunk {
  chunk_id: string;
  document_id: string;
  chunk_text: string;
  position_in_document: number;
  contextual_summary?: string | null;
  token_count?: number | null;
}

export interface RankedChunk {
  chunk: Chunk;
  score: number;
}

export interface ChatSession {
  session_id: string;
  created_at: string;
  archived_at?: string | null;
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  query_text?: string | null;
  retrieved_chunk_ids?: string[] | null;
  reranking_scores?: number[] | null;
  reranking_provider?: string | null;
  reranking_duration_ms?: number | null;
}

export interface ChatResponse {
  answer: string;
  session_id: string;
  retrieved_chunks: RankedChunk[];
  reranking_scores: number[];
  reranking_provider?: string | null;
  reranking_duration_ms?: number | null;
  response_timestamp: string;
}

export interface ApiError {
  error: string;
  detail: string;
}

// When VITE_API_BASE_URL is not set, use relative URLs (same-origin, e.g. HF Spaces)
// When running locally with separate frontend dev server, set VITE_API_BASE_URL=http://localhost:8000
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: ApiError;
    try {
      errorData = await response.json();
    } catch {
      errorData = {
        error: 'unknown_error',
        detail: `HTTP request failed with status ${response.status}`,
      };
    }
    throw errorData;
  }
  return response.json() as Promise<T>;
}

export const api = {
  // Document endpoints
  async uploadDocument(
    file: File,
    onProgress?: (progress: number) => void,
    sessionId?: string
  ): Promise<{ document_id: string; upload_timestamp: string }> {
    const formData = new FormData();
    formData.append('file', file);

    // Using XHR for progress tracking if onProgress is supplied
    if (onProgress) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const uploadUrl = `${API_BASE_URL}/documents/upload` + (sessionId ? `?session_id=${sessionId}` : '');
        xhr.open('POST', uploadUrl);
        
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percentComplete = Math.round((event.loaded / event.total) * 100);
            onProgress(percentComplete);
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText));
            } catch {
              reject({ error: 'parse_error', detail: 'Failed to parse upload response' });
            }
          } else {
            try {
              reject(JSON.parse(xhr.responseText));
            } catch {
              reject({
                error: 'upload_failed',
                detail: `Upload failed with status ${xhr.status}`,
              });
            }
          }
        };

        xhr.onerror = () => {
          reject({ error: 'network_error', detail: 'Network connection failed during upload' });
        };

        xhr.send(formData);
      });
    }

    const uploadUrl = `${API_BASE_URL}/documents/upload` + (sessionId ? `?session_id=${sessionId}` : '');
    const response = await fetch(uploadUrl, {
      method: 'POST',
      body: formData,
    });
    return handleResponse<{ document_id: string; upload_timestamp: string }>(response);
  },

  async listDocuments(limit = 10, offset = 0, sessionId?: string): Promise<DocumentMetadata[]> {
    const url = `${API_BASE_URL}/documents?limit=${limit}&offset=${offset}` + (sessionId ? `&session_id=${sessionId}` : '');
    const response = await fetch(url);
    return handleResponse<DocumentMetadata[]>(response);
  },

  async deleteDocument(documentId: string): Promise<{ status: string; document_id: string }> {
    const response = await fetch(`${API_BASE_URL}/documents/${documentId}`, {
      method: 'DELETE',
    });
    return handleResponse<{ status: string; document_id: string }>(response);
  },

  // Chat endpoints
  async createSession(): Promise<{ session_id: string }> {
    const response = await fetch(`${API_BASE_URL}/chat/session`, {
      method: 'POST',
    });
    return handleResponse<{ session_id: string }>(response);
  },

  async queryChat(sessionId: string, query: string, documentIds?: string[]): Promise<ChatResponse> {
    const response = await fetch(`${API_BASE_URL}/chat/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        session_id: sessionId,
        query,
        document_ids: documentIds,
      }),
    });
    return handleResponse<ChatResponse>(response);
  },

  async getChatHistory(sessionId: string): Promise<ChatMessage[]> {
    const response = await fetch(`${API_BASE_URL}/chat/history?session_id=${sessionId}`);
    return handleResponse<ChatMessage[]>(response);
  },

  // Config hot-reload
  async reloadConfig(): Promise<{ status: string; detail: string }> {
    const response = await fetch(`${API_BASE_URL}/config/reload`, {
      method: 'POST',
    });
    return handleResponse<{ status: string; detail: string }>(response);
  },
};
