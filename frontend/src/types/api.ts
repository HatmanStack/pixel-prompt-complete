/**
 * API Response Types for Session-based Architecture
 */

// ====================
// Model Types
// ====================

export type ModelName = 'gemini' | 'nova' | 'openai' | 'firefly';

export const MODEL_DISPLAY_NAMES: Record<ModelName, string> = {
  gemini: 'Gemini',
  nova: 'Nova Canvas',
  openai: 'DALL-E 3',
  firefly: 'Firefly',
};

export const MODELS: ModelName[] = ['gemini', 'nova', 'openai', 'firefly'];

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
  adaptedPrompt?: string;
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
  prompt: string;
  models: Record<string, { status: string; imageKey?: string; imageUrl?: string }>;
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

// Gallery list response (matches backend handle_gallery_list)
export interface GalleryListItem {
  id: string;
  timestamp: string;
  previewUrl?: string;
  imageCount: number;
}

export interface SessionGalleryListResponse {
  galleries: GalleryListItem[];
  total: number;
}

// Gallery detail response (matches backend handle_gallery_detail)
export interface GalleryDetailImage {
  key: string;
  url: string;
  model: string;
  prompt: string;
  timestamp?: string;
}

export interface SessionGalleryDetailResponse {
  galleryId: string;
  images: GalleryDetailImage[];
  total: number;
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

export interface PromptHistoryItem {
  prompt: string;
  sessionId: string;
  createdAt: number;
}

export interface PromptHistoryResponse {
  prompts: PromptHistoryItem[];
  total: number;
}

export interface DownloadResponse {
  url: string;
  filename: string;
}

export interface ApiError {
  error: string;
  code?: string;
  message?: string;
  status?: number;
  correlationId?: string;
}
