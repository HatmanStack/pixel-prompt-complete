/**
 * Mock API responses for integration testing
 */

import type {
  EnhanceResponse,
  GalleryListResponse,
  GalleryDetailResponse,
  ApiError,
} from '@/types';

interface MockJobResult {
  model: string;
  status: 'pending' | 'loading' | 'completed' | 'error';
  imageKey?: string;
  imageUrl?: string;
  completedAt?: string;
}

interface MockJobStatus {
  jobId: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  totalModels: number;
  completedModels: number;
  results: MockJobResult[];
}

export const mockGenerateResponse = {
  jobId: 'test-job-123',
  status: 'pending',
  message: 'Job created successfully',
};

export const mockJobStatusPending: MockJobStatus = {
  jobId: 'test-job-123',
  status: 'in_progress',
  totalModels: 9,
  completedModels: 0,
  results: [
    { model: 'DALL-E 3', status: 'loading' },
    { model: 'Stable Diffusion 3.5', status: 'pending' },
    { model: 'Google Gemini 2.0', status: 'pending' },
    { model: 'Imagen 3.0', status: 'pending' },
    { model: 'Amazon Nova Canvas', status: 'pending' },
    { model: 'Flux Pro 1.1', status: 'pending' },
    { model: 'Recraft V3', status: 'pending' },
    { model: 'Ideogram 2.0', status: 'pending' },
    { model: 'Midjourney v6', status: 'pending' }
  ]
};

export const mockJobStatusPartial: MockJobStatus = {
  jobId: 'test-job-123',
  status: 'in_progress',
  totalModels: 9,
  completedModels: 3,
  results: [
    {
      model: 'DALL-E 3',
      status: 'completed',
      imageKey: 'images/test-1.png',
      imageUrl: 'https://cdn.example.com/test-1.png',
      completedAt: '2025-11-16T10:30:00Z'
    },
    {
      model: 'Stable Diffusion 3.5',
      status: 'completed',
      imageKey: 'images/test-2.png',
      imageUrl: 'https://cdn.example.com/test-2.png',
      completedAt: '2025-11-16T10:30:05Z'
    },
    {
      model: 'Google Gemini 2.0',
      status: 'completed',
      imageKey: 'images/test-3.png',
      imageUrl: 'https://cdn.example.com/test-3.png',
      completedAt: '2025-11-16T10:30:10Z'
    },
    { model: 'Imagen 3.0', status: 'loading' },
    { model: 'Amazon Nova Canvas', status: 'pending' },
    { model: 'Flux Pro 1.1', status: 'pending' },
    { model: 'Recraft V3', status: 'pending' },
    { model: 'Ideogram 2.0', status: 'pending' },
    { model: 'Midjourney v6', status: 'pending' }
  ]
};

export const mockJobStatusCompleted: MockJobStatus = {
  jobId: 'test-job-123',
  status: 'completed',
  totalModels: 9,
  completedModels: 9,
  results: [
    {
      model: 'DALL-E 3',
      status: 'completed',
      imageKey: 'images/test-1.png',
      imageUrl: 'https://cdn.example.com/test-1.png',
      completedAt: '2025-11-16T10:30:00Z'
    },
    {
      model: 'Stable Diffusion 3.5',
      status: 'completed',
      imageKey: 'images/test-2.png',
      imageUrl: 'https://cdn.example.com/test-2.png',
      completedAt: '2025-11-16T10:30:05Z'
    },
    {
      model: 'Google Gemini 2.0',
      status: 'completed',
      imageKey: 'images/test-3.png',
      imageUrl: 'https://cdn.example.com/test-3.png',
      completedAt: '2025-11-16T10:30:10Z'
    },
    {
      model: 'Imagen 3.0',
      status: 'completed',
      imageKey: 'images/test-4.png',
      imageUrl: 'https://cdn.example.com/test-4.png',
      completedAt: '2025-11-16T10:30:15Z'
    },
    {
      model: 'Amazon Nova Canvas',
      status: 'completed',
      imageKey: 'images/test-5.png',
      imageUrl: 'https://cdn.example.com/test-5.png',
      completedAt: '2025-11-16T10:30:20Z'
    },
    {
      model: 'Flux Pro 1.1',
      status: 'completed',
      imageKey: 'images/test-6.png',
      imageUrl: 'https://cdn.example.com/test-6.png',
      completedAt: '2025-11-16T10:30:25Z'
    },
    {
      model: 'Recraft V3',
      status: 'completed',
      imageKey: 'images/test-7.png',
      imageUrl: 'https://cdn.example.com/test-7.png',
      completedAt: '2025-11-16T10:30:30Z'
    },
    {
      model: 'Ideogram 2.0',
      status: 'completed',
      imageKey: 'images/test-8.png',
      imageUrl: 'https://cdn.example.com/test-8.png',
      completedAt: '2025-11-16T10:30:35Z'
    },
    {
      model: 'Midjourney v6',
      status: 'completed',
      imageKey: 'images/test-9.png',
      imageUrl: 'https://cdn.example.com/test-9.png',
      completedAt: '2025-11-16T10:30:40Z'
    }
  ]
};

export const mockEnhanceResponse: EnhanceResponse = {
  original_prompt: 'cat',
  enhanced_prompt: 'A majestic orange tabby cat sitting regally on a velvet cushion, photographed in soft natural lighting',
};

export const mockGalleryListResponse: GalleryListResponse = {
  galleries: [
    {
      id: '2025-11-16-10-30-00',
      timestamp: '2025-11-16T10:30:00Z',
      prompt: 'test prompt',
      thumbnailUrl: 'https://cdn.example.com/preview-1.png',
      imageCount: 9
    },
    {
      id: '2025-11-15-14-20-00',
      timestamp: '2025-11-15T14:20:00Z',
      prompt: 'another prompt',
      thumbnailUrl: 'https://cdn.example.com/preview-2.png',
      imageCount: 8
    }
  ],
  total: 2
};

export const mockGalleryDetailResponse: GalleryDetailResponse = {
  id: '2025-11-16-10-30-00',
  prompt: 'test prompt',
  timestamp: '2025-11-16T10:30:00Z',
  images: [
    {
      model: 'DALL-E 3',
      provider: 'openai',
      url: 'https://cdn.example.com/gallery-1.png',
      status: 'success',
    },
    {
      model: 'Stable Diffusion 3.5',
      provider: 'stability',
      url: 'https://cdn.example.com/gallery-2.png',
      status: 'success',
    }
  ],
};

export const mockErrorResponse: ApiError = {
  error: 'Rate limit exceeded',
  message: 'Too many requests. Please try again later.'
};

interface ExtendedError extends Error {
  code?: string;
}

export const mockNetworkError: ExtendedError = Object.assign(
  new Error('Network request failed'),
  { code: 'NETWORK_ERROR' }
);

export const mockTimeoutError: ExtendedError = Object.assign(
  new Error('Request timeout - server took too long to respond'),
  { code: 'TIMEOUT' }
);
