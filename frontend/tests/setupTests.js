/**
 * Test setup file for Vitest
 * This file runs before each test file to configure testing environment
 */

import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Mock HTMLMediaElement for jsdom (audio/video)
window.HTMLMediaElement.prototype.pause = vi.fn();
window.HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
window.HTMLMediaElement.prototype.load = vi.fn();

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(() => null),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
