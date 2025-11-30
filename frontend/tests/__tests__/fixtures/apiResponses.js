/**
 * Mock API responses for integration testing
 */

export const mockGenerateResponse = {
  jobId: 'test-job-123',
  message: 'Job created successfully',
  totalModels: 9
};

export const mockJobStatusPending = {
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

export const mockJobStatusPartial = {
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

export const mockJobStatusCompleted = {
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

export const mockEnhanceResponse = {
  original: 'cat',
  enhanced: 'A majestic orange tabby cat sitting regally on a velvet cushion, photographed in soft natural lighting',
  short_prompt: 'An orange tabby cat on a velvet cushion',
  long_prompt: 'A majestic orange tabby cat sitting regally on a velvet cushion, photographed in soft natural lighting with a shallow depth of field, warm color palette, professional pet photography style'
};

export const mockGalleryListResponse = {
  galleries: [
    {
      id: '2025-11-16-10-30-00',
      timestamp: '2025-11-16T10:30:00Z',
      preview: 'https://cdn.example.com/preview-1.png',
      imageCount: 9
    },
    {
      id: '2025-11-15-14-20-00',
      timestamp: '2025-11-15T14:20:00Z',
      preview: 'https://cdn.example.com/preview-2.png',
      imageCount: 8
    }
  ],
  total: 2
};

export const mockGalleryDetailResponse = {
  galleryId: '2025-11-16-10-30-00',
  images: [
    {
      key: 'images/gallery-1.png',
      url: 'https://cdn.example.com/gallery-1.png',
      model: 'DALL-E 3',
      prompt: 'test prompt',
      steps: 28,
      guidance: 5,
      timestamp: '2025-11-16T10:30:00Z'
    },
    {
      key: 'images/gallery-2.png',
      url: 'https://cdn.example.com/gallery-2.png',
      model: 'Stable Diffusion 3.5',
      prompt: 'test prompt',
      steps: 28,
      guidance: 5,
      timestamp: '2025-11-16T10:30:05Z'
    }
  ],
  total: 2
};

export const mockErrorResponse = {
  error: 'Rate limit exceeded',
  message: 'Too many requests. Please try again later.'
};

export const mockNetworkError = new Error('Network request failed');
mockNetworkError.code = 'NETWORK_ERROR';

export const mockTimeoutError = new Error('Request timeout - server took too long to respond');
mockTimeoutError.code = 'TIMEOUT';
