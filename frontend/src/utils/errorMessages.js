/**
 * Error Message Mapping
 * Maps HTTP status codes and error types to user-friendly messages
 */

/**
 * Error message templates based on HTTP status codes
 */
export const ERROR_MESSAGES = {
  // Client Errors (4xx)
  400: {
    title: 'Invalid Request',
    message: 'There was a problem with your request. Please check your input and try again.',
    icon: '⚠️',
    retryable: false,
  },
  401: {
    title: 'Unauthorized',
    message: 'You are not authorized to perform this action.',
    icon: '🔒',
    retryable: false,
  },
  403: {
    title: 'Access Denied',
    message: 'You do not have permission to access this resource.',
    icon: '🚫',
    retryable: false,
  },
  404: {
    title: 'Not Found',
    message: 'The requested resource could not be found.',
    icon: '❓',
    retryable: false,
  },
  429: {
    title: 'Rate Limit Exceeded',
    message: 'You have made too many requests. Please wait {retryAfter} and try again.',
    icon: '⏱️',
    retryable: true,
  },

  // Server Errors (5xx)
  500: {
    title: 'Server Error',
    message: 'An unexpected error occurred on the server. Please try again in a few minutes.',
    icon: '❌',
    retryable: true,
  },
  502: {
    title: 'Bad Gateway',
    message: 'The server received an invalid response. Please try again.',
    icon: '❌',
    retryable: true,
  },
  503: {
    title: 'Service Unavailable',
    message: 'The service is temporarily unavailable. Please try again in a moment.',
    icon: '⚠️',
    retryable: true,
  },
  504: {
    title: 'Gateway Timeout',
    message: 'The request took too long to complete. Please try again.',
    icon: '⏱️',
    retryable: true,
  },

  // Network Errors
  NETWORK_ERROR: {
    title: 'Connection Failed',
    message: 'Unable to connect to the server. Please check your internet connection and try again.',
    icon: '📡',
    retryable: true,
  },
  TIMEOUT: {
    title: 'Request Timeout',
    message: 'The request took too long to complete. Please try again.',
    icon: '⏱️',
    retryable: true,
  },

  // Default
  DEFAULT: {
    title: 'Error',
    message: 'An unexpected error occurred. Please try again.',
    icon: '❌',
    retryable: true,
  },
};

/**
 * Specific error code messages (override status code messages)
 */
export const SPECIFIC_ERROR_MESSAGES = {
  RATE_LIMIT_EXCEEDED: {
    title: 'Rate Limit Exceeded',
    message: 'You have exceeded the rate limit. Please wait {retryAfter} before trying again.',
    icon: '⏱️',
    retryable: true,
  },
  INAPPROPRIATE_CONTENT: {
    title: 'Content Filtered',
    message: 'Your prompt contains inappropriate content and cannot be processed. Please revise your prompt.',
    icon: '🚫',
    retryable: false,
  },
  PROMPT_TOO_LONG: {
    title: 'Prompt Too Long',
    message: 'Your prompt exceeds the maximum length of {maxLength} characters. Please shorten it.',
    icon: '⚠️',
    retryable: false,
  },
  PROMPT_REQUIRED: {
    title: 'Prompt Required',
    message: 'Please enter a prompt to generate images.',
    icon: 'ℹ️',
    retryable: false,
  },
  JOB_NOT_FOUND: {
    title: 'Job Not Found',
    message: 'The requested job could not be found. It may have expired.',
    icon: '❓',
    retryable: false,
  },
  INVALID_JSON: {
    title: 'Invalid Request',
    message: 'The request data is invalid. Please try again.',
    icon: '⚠️',
    retryable: false,
  },
};

/**
 * Get error message for a given error
 * @param {Error|Object} error - Error object or HTTP error response
 * @returns {Object} Error message object with title, message, icon, retryable
 */
export function getErrorMessage(error) {
  // Check for specific error code first
  if (error.code && SPECIFIC_ERROR_MESSAGES[error.code]) {
    return formatErrorMessage(SPECIFIC_ERROR_MESSAGES[error.code], error);
  }

  // Check for HTTP status code
  if (error.status && ERROR_MESSAGES[error.status]) {
    return formatErrorMessage(ERROR_MESSAGES[error.status], error);
  }

  // Check for network error
  if (error.code === 'TIMEOUT' || error.name === 'AbortError') {
    return formatErrorMessage(ERROR_MESSAGES.TIMEOUT, error);
  }

  if (!error.status) {
    return formatErrorMessage(ERROR_MESSAGES.NETWORK_ERROR, error);
  }

  // Default error message
  return formatErrorMessage(ERROR_MESSAGES.DEFAULT, error);
}

/**
 * Format error message with dynamic values
 * @param {Object} template - Error message template
 * @param {Error|Object} error - Error object
 * @returns {Object} Formatted error message
 */
function formatErrorMessage(template, error) {
  let message = template.message;

  // Replace {retryAfter} placeholder
  if (error.retryAfter) {
    message = message.replace('{retryAfter}', formatRetryAfter(error.retryAfter));
  }

  // Replace {maxLength} placeholder
  if (error.maxLength) {
    message = message.replace('{maxLength}', error.maxLength);
  }

  return {
    ...template,
    message,
    originalError: error.message || String(error),
  };
}

/**
 * Format retry-after time in human-readable format
 * @param {number} seconds - Seconds until retry is allowed
 * @returns {string} Formatted time string
 */
function formatRetryAfter(seconds) {
  if (seconds < 60) {
    return `${seconds} second${seconds !== 1 ? 's' : ''}`;
  }

  const minutes = Math.ceil(seconds / 60);
  return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
}

/**
 * Get field-specific error message for validation errors
 * @param {string} field - Field name
 * @param {string} constraint - Constraint that was violated
 * @returns {string} Specific error message
 */
export function getValidationMessage(field, constraint) {
  const messages = {
    prompt: {
      required: 'Prompt is required',
      tooLong: 'Prompt is too long (maximum 1000 characters)',
      tooShort: 'Prompt is too short (minimum 3 characters)',
    },
    steps: {
      min: 'Steps must be at least 1',
      max: 'Steps cannot exceed 100',
    },
    guidance: {
      min: 'Guidance must be at least 1',
      max: 'Guidance cannot exceed 20',
    },
  };

  return messages[field]?.[constraint] || `${field} is invalid`;
}
