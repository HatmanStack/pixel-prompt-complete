/**
 * Image Helper Utilities
 * Functions for handling image loading, conversion, and blob URLs
 */

interface ImageJsonData {
  output?: string;
  [key: string]: unknown;
}

/**
 * Convert base64 string to Blob
 */
export function base64ToBlob(base64: string, mimeType = 'image/png'): Blob {
  // Remove data URL prefix if present
  const base64Data = base64.replace(/^data:image\/\w+;base64,/, '');

  // Decode base64
  const binaryString = atob(base64Data);
  const bytes = new Uint8Array(binaryString.length);

  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }

  return new Blob([bytes], { type: mimeType });
}

/**
 * Create object URL from Blob
 */
export function createBlobUrl(blob: Blob): string {
  return URL.createObjectURL(blob);
}

/**
 * Revoke object URL to prevent memory leaks
 */
export function revokeBlobUrl(url: string | null | undefined): void {
  if (url && url.startsWith('blob:')) {
    URL.revokeObjectURL(url);
  }
}

/**
 * Fetch image JSON from S3/CloudFront
 */
export async function fetchImageFromS3(
  imageKey: string,
  cloudFrontDomain: string,
): Promise<ImageJsonData> {
  try {
    // Build CloudFront URL
    const url = imageKey.startsWith('http') ? imageKey : `https://${cloudFrontDomain}/${imageKey}`;

    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to fetch image: ${response.status}`);
    }

    const data: ImageJsonData = await response.json();
    return data;
  } catch (error) {
    console.error('Error fetching image from S3:', error);
    throw error;
  }
}

/**
 * Convert base64 image to blob URL
 */
export function base64ToBlobUrl(base64: string): string {
  const blob = base64ToBlob(base64);
  return createBlobUrl(blob);
}

/**
 * Preload image to ensure it's cached
 */
export function preloadImage(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve();
    img.onerror = () => reject(new Error(`Failed to load image: ${url}`));
    img.src = url;
  });
}

/**
 * Download image to user's device
 */
export function downloadImage(url: string, filename: string): void {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
