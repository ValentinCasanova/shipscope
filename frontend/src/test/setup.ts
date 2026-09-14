import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Testing Library only registers automatic cleanup when test globals exist, and
// Vitest globals are off, so unmount rendered components after each test here.
afterEach(() => {
  cleanup();
});
