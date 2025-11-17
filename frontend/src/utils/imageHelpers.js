/**
 * Image Helper Utilities
 * Functions for handling image loading, conversion, and blob URLs
 */

/**
 * Convert base64 string to Blob
 * @param {string} base64 - Base64 encoded image
 * @param {string} mimeType - MIME type (default: image/png)
 * @returns {Blob} Blob object
 */
export function base64ToBlob(base64, mimeType = 'image/png') {
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
 * @param {Blob} blob - Blob object
 * @returns {string} Object URL
 */
export function createBlobUrl(blob) {
  return URL.createObjectURL(blob);
}

/**
 * Revoke object URL to prevent memory leaks
 * @param {string} url - Object URL to revoke
 */
export function revokeBlobUrl(url) {
  if (url && url.startsWith('blob:')) {
    URL.revokeObjectURL(url);
  }
}

/**
 * Fetch image JSON from S3/CloudFront
 * @param {string} imageKey - S3 key or CloudFront URL
 * @param {string} cloudFrontDomain - CloudFront domain
 * @returns {Promise<Object>} Image JSON data
 */
export async function fetchImageFromS3(imageKey, cloudFrontDomain) {
  try {
    // Build CloudFront URL
    const url = imageKey.startsWith('http')
      ? imageKey
      : `https://${cloudFrontDomain}/${imageKey}`;

    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to fetch image: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error fetching image from S3:', error);
    throw error;
  }
}

/**
 * Convert base64 image to blob URL
 * @param {string} base64 - Base64 encoded image
 * @returns {string} Blob URL
 */
export function base64ToBlobUrl(base64) {
  const blob = base64ToBlob(base64);
  return createBlobUrl(blob);
}

/**
 * Preload image to ensure it's cached
 * @param {string} url - Image URL
 * @returns {Promise<void>}
 */
export function preloadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve();
    img.onerror = () => reject(new Error(`Failed to load image: ${url}`));
    img.src = url;
  });
}

/**
 * Download image to user's device
 * @param {string} url - Image URL (blob or http)
 * @param {string} filename - Filename for download
 */
export function downloadImage(url, filename) {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
