/**
 * Mock API responses for testing
 */

export const mockGenerateResponse = {
  jobId: 'test-job-123',
  status: 'in_progress',
  message: 'Job started'
};

export const mockJobStatusPending = {
  jobId: 'test-job-123',
  status: 'in_progress',
  completedModels: 0,
  totalModels: 9,
  results: Array(9).fill(null).map((_, i) => ({
    model: `Model ${i + 1}`,
    status: 'pending'
  }))
};

export const mockJobStatusPartial = {
  jobId: 'test-job-123',
  status: 'in_progress',
  completedModels: 3,
  totalModels: 9,
  results: [
    { model: 'DALL-E 3', status: 'completed', image: 'data:image/png;base64,iVBORw0KGgo=' },
    { model: 'Gemini 2.0', status: 'completed', image: 'data:image/png;base64,iVBORw0KGgo=' },
    { model: 'Flux Pro', status: 'completed', image: 'data:image/png;base64,iVBORw0KGgo=' },
    { model: 'Model 4', status: 'loading' },
    { model: 'Model 5', status: 'loading' },
    { model: 'Model 6', status: 'pending' },
    { model: 'Model 7', status: 'pending' },
    { model: 'Model 8', status: 'pending' },
    { model: 'Model 9', status: 'pending' }
  ]
};

export const mockJobStatusCompleted = {
  jobId: 'test-job-123',
  status: 'completed',
  completedModels: 9,
  totalModels: 9,
  results: Array(9).fill(null).map((_, i) => ({
    model: `Model ${i + 1}`,
    status: 'completed',
    image: 'data:image/png;base64,iVBORw0KGgo='
  }))
};

// Update first 3 models with realistic names
mockJobStatusCompleted.results[0].model = 'DALL-E 3';
mockJobStatusCompleted.results[1].model = 'Gemini 2.0';
mockJobStatusCompleted.results[2].model = 'Flux Pro';

export const mockEnhanceResponse = {
  short_prompt: 'A beautiful orange tabby cat on a velvet cushion',
  long_prompt: 'A majestic orange tabby cat sitting regally on a velvet cushion in golden afternoon light'
};

export const mockGalleryListResponse = {
  galleries: [
    { id: 'gallery-1', timestamp: '2024-01-15T10:30:00Z', imageCount: 9 },
    { id: 'gallery-2', timestamp: '2024-01-14T15:20:00Z', imageCount: 7 }
  ],
  total: 2
};

export const mockGalleryDetailResponse = {
  galleryId: 'gallery-1',
  images: Array(9).fill(null).map((_, i) => ({
    model: `Model ${i + 1}`,
    url: `https://cdn.example.com/image-${i}.png`,
    timestamp: '2024-01-15T10:30:00Z'
  })),
  total: 9
};
