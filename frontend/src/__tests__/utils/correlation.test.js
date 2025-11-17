/**
 * Tests for correlation ID utility
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  generateCorrelationId,
  getCorrelationId,
  clearCorrelationId,
  setCorrelationId,
} from '../../utils/correlation';

describe('Correlation ID Utility', () => {
  beforeEach(() => {
    clearCorrelationId();
  });

  it('should generate a valid UUID v4', () => {
    const id = generateCorrelationId();
    expect(id).toBeTruthy();
    expect(typeof id).toBe('string');
    // UUIDv4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  });

  it('should generate unique IDs', () => {
    const id1 = generateCorrelationId();
    const id2 = generateCorrelationId();
    expect(id1).not.toBe(id2);
  });

  it('should return same ID from getCorrelationId() until cleared', () => {
    const id1 = getCorrelationId();
    const id2 = getCorrelationId();
    expect(id1).toBe(id2);
  });

  it('should generate new ID after clearing', () => {
    const id1 = getCorrelationId();
    clearCorrelationId();
    const id2 = getCorrelationId();
    expect(id1).not.toBe(id2);
  });

  it('should allow setting specific correlation ID', () => {
    const customId = 'test-correlation-123';
    setCorrelationId(customId);
    expect(getCorrelationId()).toBe(customId);
  });

  it('should clear custom correlation ID', () => {
    setCorrelationId('custom-id');
    clearCorrelationId();
    const newId = getCorrelationId();
    expect(newId).not.toBe('custom-id');
    expect(newId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  });
});
