/**
 * Tests for error logging utility
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  logError,
  logWarning,
  logInfo,
  logDebug,
  serializeError,
  getBrowserMetadata,
} from '../../utils/logger';

// Mock fetch globally
global.fetch = vi.fn();

// Mock navigator and window
global.navigator = {
  userAgent: 'Mozilla/5.0 (Test Browser)',
};
global.window = {
  innerWidth: 1920,
  innerHeight: 1080,
  location: {
    href: 'http://localhost:3000/test',
  },
};

describe('Logger Utility', () => {
  beforeEach(() => {
    fetch.mockClear();
    fetch.mockResolvedValue({
      ok: true,
      status: 200,
    });
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  describe('serializeError', () => {
    it('should serialize error object', () => {
      const error = new Error('Test error');
      const serialized = serializeError(error);

      expect(serialized.message).toBe('Test error');
      expect(serialized.name).toBe('Error');
      expect(serialized.stack).toBeTruthy();
      expect(serialized.stack).toContain('Test error');
    });

    it('should handle error without stack', () => {
      const error = { message: 'Simple error' };
      const serialized = serializeError(error);

      expect(serialized.message).toBe('Simple error');
      expect(serialized.stack).toBe('');
    });

    it('should handle null error', () => {
      const serialized = serializeError(null);
      expect(serialized).toEqual({});
    });
  });

  describe('getBrowserMetadata', () => {
    it('should return browser information', () => {
      const metadata = getBrowserMetadata();

      expect(metadata.userAgent).toBe('Mozilla/5.0 (Test Browser)');
      expect(metadata.viewport).toBe('1920x1080');
      expect(metadata.url).toBe('http://localhost:3000/test');
      expect(metadata.timestamp).toBeTruthy();
    });
  });

  describe('logError', () => {
    it('should send error log to backend', async () => {
      const error = new Error('Test error');
      await logError('Error occurred', error, { component: 'TestComponent' });

      expect(fetch).toHaveBeenCalledTimes(1);
      const [url, options] = fetch.mock.calls[0];

      expect(url).toContain('/log');
      expect(options.method).toBe('POST');
      expect(options.headers['Content-Type']).toBe('application/json');
      expect(options.headers['X-Correlation-ID']).toBeTruthy();

      const body = JSON.parse(options.body);
      expect(body.level).toBe('ERROR');
      expect(body.message).toBe('Error occurred');
      expect(body.stack).toContain('Test error');
      expect(body.metadata.component).toBe('TestComponent');
      expect(body.metadata.userAgent).toBeTruthy();
    });

    it('should handle custom correlation ID', async () => {
      await logError('Test error', null, { correlationId: 'custom-123' });

      const [, options] = fetch.mock.calls[0];
      expect(options.headers['X-Correlation-ID']).toBe('custom-123');
    });

    it('should deduplicate identical errors', async () => {
      const error = new Error('Duplicate error');

      await logError('Error 1', error);
      await logError('Error 1', error); // Should be deduplicated

      // Only one call should be made
      expect(fetch).toHaveBeenCalledTimes(1);
    });

    it('should not deduplicate different errors', async () => {
      const error1 = new Error('Error 1');
      const error2 = new Error('Error 2');

      await logError('First error', error1);
      await logError('Second error', error2);

      expect(fetch).toHaveBeenCalledTimes(2);
    });
  });

  describe('logWarning', () => {
    it('should send warning log to backend', async () => {
      await logWarning('Warning message', { component: 'TestComponent' });

      expect(fetch).toHaveBeenCalledTimes(1);
      const body = JSON.parse(fetch.mock.calls[0][1].body);

      expect(body.level).toBe('WARNING');
      expect(body.message).toBe('Warning message');
      expect(body.metadata.component).toBe('TestComponent');
    });
  });

  describe('logInfo', () => {
    it('should send info log to backend', async () => {
      await logInfo('Info message', { action: 'user_click' });

      expect(fetch).toHaveBeenCalledTimes(1);
      const body = JSON.parse(fetch.mock.calls[0][1].body);

      expect(body.level).toBe('INFO');
      expect(body.message).toBe('Info message');
      expect(body.metadata.action).toBe('user_click');
    });
  });

  describe('logDebug', () => {
    it('should send debug log to backend', async () => {
      await logDebug('Debug message', { debugInfo: 'test' });

      expect(fetch).toHaveBeenCalledTimes(1);
      const body = JSON.parse(fetch.mock.calls[0][1].body);

      expect(body.level).toBe('DEBUG');
      expect(body.message).toBe('Debug message');
      expect(body.metadata.debugInfo).toBe('test');
    });
  });

  describe('error handling', () => {
    it('should fail silently on network error', async () => {
      fetch.mockRejectedValueOnce(new Error('Network error'));

      // Should not throw
      await expect(logError('Test error')).resolves.toBeUndefined();
    });

    it('should fail silently on 500 response', async () => {
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      // Should not throw
      await expect(logError('Test error')).resolves.toBeUndefined();
    });
  });
});
