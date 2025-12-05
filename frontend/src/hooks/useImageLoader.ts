/**
 * useImageLoader Hook
 * Handles progressive image loading from job status
 */

import { useState, useEffect, useRef } from 'react';
import { base64ToBlobUrl, revokeBlobUrl, fetchImageFromS3 } from '@/utils/imageHelpers';
import type { StatusResponse, ImageResult } from '@/types';

interface JobResult extends ImageResult {
  output?: string;
  imageUrl?: string;
  completedAt?: string;
}

interface UseImageLoaderReturn {
  images: (string | null)[];
  loadingStates: boolean[];
  errors: (string | null)[];
}

interface BlobUrlsRef {
  urls: string[];
  jobId?: string;
}

/**
 * Custom hook for loading images progressively as they complete
 */
function useImageLoader(
  jobStatus: StatusResponse | null,
  cloudFrontDomain = ''
): UseImageLoaderReturn {
  const [images, setImages] = useState<(string | null)[]>(Array(9).fill(null));
  const [loadingStates, setLoadingStates] = useState<boolean[]>(Array(9).fill(false));
  const [errors, setErrors] = useState<(string | null)[]>(Array(9).fill(null));

  // Track blob URLs for cleanup
  const blobUrlsRef = useRef<BlobUrlsRef>({ urls: [] });
  // Track which images have been fetched
  const fetchedRef = useRef<Set<string>>(new Set());
  // Track current job ID to prevent cross-job contamination
  const currentJobIdRef = useRef<string | null>(null);

  // Cleanup blob URLs on unmount
  useEffect(() => {
    return () => {
      blobUrlsRef.current.urls.forEach((url) => revokeBlobUrl(url));
      blobUrlsRef.current.urls = [];
    };
  }, []);

  // Load images when job status updates
  useEffect(() => {
    if (!jobStatus || !jobStatus.results) {
      return;
    }

    const currentJobId = jobStatus.jobId;
    currentJobIdRef.current = currentJobId;

    const loadImage = async (result: JobResult, index: number) => {
      // Skip if already fetched
      const fetchKey = `${index}-${result.completedAt || ''}`;
      if (fetchedRef.current.has(fetchKey)) {
        return;
      }

      // Skip if no image data available yet
      if (!result.output && !result.imageUrl) {
        return;
      }

      // Mark as loading (only after confirming we have data to load)
      setLoadingStates((prev) => {
        const newStates = [...prev];
        newStates[index] = true;
        return newStates;
      });

      try {
        let imageUrl: string;

        // If result has base64 output, convert it
        if (result.output) {
          imageUrl = base64ToBlobUrl(result.output);
          blobUrlsRef.current.urls.push(imageUrl);
        }
        // If result has imageUrl (S3 key), fetch from CloudFront
        else if (result.imageUrl) {
          const imageData = await fetchImageFromS3(result.imageUrl, cloudFrontDomain);

          // Check if job changed during async fetch
          if (currentJobIdRef.current !== currentJobId) {
            return;
          }

          if (imageData.output) {
            imageUrl = base64ToBlobUrl(imageData.output);
            blobUrlsRef.current.urls.push(imageUrl);
          } else {
            throw new Error('No image data in response');
          }
        } else {
          throw new Error('No image source available');
        }

        // Check again if job changed before updating state
        if (currentJobIdRef.current !== currentJobId) {
          return;
        }

        // Update image
        setImages((prev) => {
          const newImages = [...prev];
          newImages[index] = imageUrl;
          return newImages;
        });

        // Mark as loaded
        setLoadingStates((prev) => {
          const newStates = [...prev];
          newStates[index] = false;
          return newStates;
        });

        // Mark as fetched
        fetchedRef.current.add(fetchKey);
      } catch (error) {
        console.error(`[IMAGE_LOADER] Error loading image ${index}:`, error);

        // Check if job changed during error handling
        if (currentJobIdRef.current !== currentJobId) {
          return;
        }

        // Set error
        setErrors((prev) => {
          const newErrors = [...prev];
          newErrors[index] = error instanceof Error ? error.message : 'Failed to load image';
          return newErrors;
        });

        // Mark as not loading
        setLoadingStates((prev) => {
          const newStates = [...prev];
          newStates[index] = false;
          return newStates;
        });
      }
    };

    // Load all completed images
    (jobStatus.results as JobResult[]).forEach((result, index) => {
      if (result.status === 'success' && !images[index]) {
        loadImage(result, index);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobStatus, cloudFrontDomain]);

  // Reset when job changes
  useEffect(() => {
    if (jobStatus?.jobId !== blobUrlsRef.current.jobId) {
      // Cleanup old blob URLs
      blobUrlsRef.current.urls.forEach((url) => revokeBlobUrl(url));
      blobUrlsRef.current = { urls: [], jobId: jobStatus?.jobId };

      // Reset state
      setImages(Array(9).fill(null));
      setLoadingStates(Array(9).fill(false));
      setErrors(Array(9).fill(null));
      fetchedRef.current.clear();
    }
  }, [jobStatus?.jobId]);

  return {
    images,
    loadingStates,
    errors,
  };
}

export default useImageLoader;
