import { test, expect } from '@playwright/test';

test.describe('RAG Chatbot Workspace E2E Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept chat session creation
    await page.route('**/chat/session', async (route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ session_id: 'e2e-session-uuid' }),
      });
    });

    // Intercept config reload
    await page.route('**/config/reload', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success', detail: 'Configuration reloaded successfully.' }),
      });
    });
  });

  test('should load page, upload file, poll status, reload config, and execute chat queries', async ({ page }) => {
    // 1. Setup mock states
    let documentList: any[] = [];
    
    // Intercept GET /documents
    await page.route('**/documents?limit=*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(documentList),
      });
    });

    // Intercept POST /documents/upload
    await page.route('**/documents/upload', async (route) => {
      documentList = [
        {
          document_id: 'e2e-doc-uuid',
          filename: 'contract.pdf',
          upload_timestamp: new Date().toISOString(),
          file_size_bytes: 4096,
          format: 'pdf',
          processing_status: 'completed',
        },
      ];
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          document_id: 'e2e-doc-uuid',
          upload_timestamp: new Date().toISOString(),
        }),
      });
    });

    // Intercept POST /chat/query
    await page.route('**/chat/query', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          answer: 'This is an E2E mocked answer grounded in contract.',
          session_id: 'e2e-session-uuid',
          retrieved_chunks: [
            {
              chunk: {
                chunk_id: 'chunk-1',
                document_id: 'e2e-doc-uuid',
                chunk_text: 'The payment terms are Net 30.',
                position_in_document: 0,
                contextual_summary: 'Terms context summary.',
              },
              score: 0.985,
            },
          ],
          reranking_scores: [0.985],
          response_timestamp: new Date().toISOString(),
        }),
      });
    });

    // 2. Load the App
    await page.goto('/');
    await expect(page.locator('h1')).toHaveText('RAG Chatbot Workspace');
    await expect(page.getByTestId('empty-state')).toBeVisible();

    // 3. Trigger config reload
    await page.getByTestId('reload-config-btn').click();
    await expect(page.getByTestId('toast-success')).toBeVisible();
    await expect(page.getByText('Configuration reloaded successfully.')).toBeVisible();

    // Dismiss toast by clicking close element
    await page.locator('button[aria-label="Close notification"]').click();

    // 4. Perform upload
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByTestId('dropzone').click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles({
      name: 'contract.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4\nMock contract content'),
    });

    // Verify upload success toast
    await expect(page.getByTestId('toast-success')).toBeVisible();
    await expect(page.getByText('"contract.pdf" uploaded successfully!')).toBeVisible();

    // Verify document listed in management base
    await expect(page.getByTestId('document-item')).toBeVisible();
    await expect(page.getByTestId('document-item').locator('.doc-name')).toHaveText('contract.pdf');
    await expect(page.getByTestId('status-completed')).toHaveText('completed');

    // 5. Send Chat Query
    const input = page.getByTestId('chat-input');
    await input.fill('What are the payment terms?');
    await page.getByTestId('send-btn').click();

    // Check query rendered in chronological chat logs
    await expect(page.getByTestId('message-user')).toContainText('What are the payment terms?');
    
    // Check answer text and references
    await expect(page.getByTestId('message-assistant')).toContainText(
      'This is an E2E mocked answer grounded in contract.'
    );

    // Expand citations
    const citationsToggle = page.getByTestId('sources-toggle');
    await expect(citationsToggle).toContainText('Cited Sources (1)');
    await citationsToggle.click();

    // Assert citations visible
    await expect(page.getByTestId('source-item')).toBeVisible();
    await expect(page.getByText('The payment terms are Net 30.')).toBeVisible();
  });
});
