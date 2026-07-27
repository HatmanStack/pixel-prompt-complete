/**
 * Image Helper Utilities
 * Functions for handling image loading, conversion, and blob URLs
 */

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
