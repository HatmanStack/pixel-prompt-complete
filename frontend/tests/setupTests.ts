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

// Mock useSound hook globally - Audio constructor doesn't work with vitest 4 mocks
vi.mock('@/hooks/useSound', () => ({
  useSound: () => ({
    playSound: vi.fn(),
    soundsLoaded: true,
  }),
}));

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(() => null),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Mock matchMedia for responsive components
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
