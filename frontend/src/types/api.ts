/**
 * API Response Types
 */

export type JobStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export interface ImageResult {
  model: string;
  provider: string;
  url: string;
  status: 'success' | 'error';
  error?: string;
}

export interface Job {
  jobId: string;
  status: JobStatus;
  prompt: string;
  createdAt: string;
  completedAt?: string;
  results: ImageResult[];
  modelCount: number;
}

export interface GenerateResponse {
  jobId: string;
  status: JobStatus;
  message?: string;
}

export interface StatusResponse extends Job {}

export interface EnhanceResponse {
  short_prompt?: string;
  long_prompt?: string;
  enhanced_prompt?: string;
  original_prompt?: string;
}

export interface GalleryPreview {
  id: string;
  timestamp: string;
  prompt: string;
  thumbnailUrl: string;
  imageCount: number;
}

export interface GalleryListResponse {
  galleries: GalleryPreview[];
  total: number;
}

export interface GalleryDetailResponse {
  id: string;
  prompt: string;
  timestamp: string;
  images: ImageResult[];
}

export interface ApiError {
  error: string;
  code?: string;
  message?: string;
  status?: number;
  correlationId?: string;
}
