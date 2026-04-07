/**
 * Tests for correlation ID utility
 */

import { describe, it, expect } from 'vitest';
import { generateCorrelationId } from '@/utils/correlation';

describe('Correlation ID Utility', () => {
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
});
