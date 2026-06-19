import '@testing-library/jest-dom';
import { vi } from 'vitest';

HTMLElement.prototype.scrollIntoView = vi.fn();
