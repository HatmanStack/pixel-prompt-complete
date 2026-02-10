/**
 * API Response Types for Session-based Architecture
 */

// ====================
// Model Types
// ====================

export type ModelName = 'flux' | 'recraft' | 'gemini' | 'openai';

export const MODEL_DISPLAY_NAMES: Record<ModelName, string> = {
  flux: 'Flux',
  recraft: 'Recraft',
  gemini: 'Gemini',
  openai: 'OpenAI',
};

export const MODELS: ModelName[] = ['flux', 'recraft', 'gemini', 'openai'];

// ====================
// Iteration Types
// ====================

// Status values from backend API (in_progress) are mapped to 'loading' in frontend
// 'disabled' is used for models that are not enabled
export type IterationStatus =
  | 'pending'
  | 'loading'
  | 'in_progress'
  | 'completed'
  | 'error'
  | 'disabled'
  | 'partial';

export interface Iteration {
  index: number;
  status: IterationStatus;
  prompt: string;
  imageUrl?: string;
  error?: string;
  completedAt?: string;
}

// ====================
// Model Column Types
// ====================

export interface ModelColumn {
  name: ModelName;
  enabled: boolean;
  status: IterationStatus;
  iterations: Iteration[];
}

// ====================
// Session Types
// ====================

export type SessionStatus = 'pending' | 'in_progress' | 'completed' | 'partial' | 'failed';

export interface Session {
  sessionId: string;
  status: SessionStatus;
  prompt: string;
  createdAt: string;
  updatedAt: string;
  models: Record<ModelName, ModelColumn>;
}

export interface SessionPreview {
  sessionId: string;
  prompt: string;
  thumbnail: string;
  totalIterations: number;
  createdAt: string;
}

// ====================
// API Response Types
// ====================

// New session-based generate response
export interface SessionGenerateResponse {
  sessionId: string;
  status: string;
}

export interface IterateResponse {
  sessionId: string;
  model: ModelName;
  iteration: number;
  status: string;
}

export interface OutpaintResponse {
  sessionId: string;
  model: ModelName;
  iteration: number;
  status: string;
}

export type OutpaintPreset = '16:9' | '9:16' | '1:1' | '4:3' | 'expand_all';

export interface EnhanceResponse {
  short_prompt?: string;
  long_prompt?: string;
  enhanced_prompt?: string;
  original_prompt?: string;
}

// New session-based gallery list response
export interface SessionGalleryListResponse {
  sessions: SessionPreview[];
  total: number;
}

// New session-based gallery detail response
export interface SessionGalleryDetailResponse {
  session: Session;
}

// ====================
// Selection Types
// ====================

export interface SelectionState {
  selectedModels: Set<ModelName>;
  isMultiSelectMode: boolean;
}

// ====================
// Error Types
// ====================

export interface ApiError {
  error: string;
  code?: string;
  message?: string;
  status?: number;
  correlationId?: string;
}
