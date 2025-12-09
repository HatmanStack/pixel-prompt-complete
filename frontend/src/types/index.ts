/**
 * Type Definitions Index
 * Re-exports all types for convenient importing
 */

// API types - New session-based types
export type {
  ModelName,
  IterationStatus,
  Iteration,
  ModelColumn,
  SessionStatus,
  Session,
  SessionPreview,
  SessionGenerateResponse,
  IterateResponse,
  OutpaintResponse,
  OutpaintPreset,
  EnhanceResponse,
  SessionGalleryListResponse,
  SessionGalleryDetailResponse,
  SelectionState,
  ApiError,
  // Legacy types (for backwards compatibility)
  JobStatus,
  ImageResult,
  Job,
  StatusResponse,
  GalleryPreview,
  GenerateResponse,
  GalleryListResponse,
  GalleryDetailResponse,
} from './api';

// API constants
export { MODEL_DISPLAY_NAMES, MODELS } from './api';

// Store types
export type {
  ViewType,
  SoundName,
  AppState,
  AppActions,
  AppStore,
  UIState,
  UIActions,
  UIStore,
} from './store';

// Component types
export type {
  BaseProps,
  WithChildren,
  WithOptionalChildren,
  Clickable,
  InputProps,
  ButtonProps,
  ModalProps,
  ImageDisplayProps,
  LayoutProps,
} from './components';
