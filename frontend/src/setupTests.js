/**
 * Test setup file for Vitest
 * This file runs before each test file to configure testing environment
 */

import '@testing-library/jest-dom';

// Clean up after each test automatically
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});
