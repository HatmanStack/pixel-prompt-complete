/**
 * Shared Component Prop Types
 */

import type { ReactNode, ElementType } from 'react';

/**
 * Base props that most components should extend
 */
export interface BaseProps {
  className?: string;
  testId?: string;
}

/**
 * Props for components that can have children
 */
export interface WithChildren {
  children: ReactNode;
}

/**
 * Props for components with optional children
 */
export interface WithOptionalChildren {
  children?: ReactNode;
}

/**
 * Props for components that handle click events
 */
export interface Clickable {
  onClick?: () => void;
  disabled?: boolean;
}

/**
 * Props for form input components
 */
export interface InputProps extends BaseProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  maxLength?: number;
  autoFocus?: boolean;
}

/**
 * Props for button components
 */
export interface ButtonProps extends BaseProps, Clickable {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  fullWidth?: boolean;
  type?: 'button' | 'submit' | 'reset';
  ariaLabel?: string;
}

/**
 * Props for modal components
 */
export interface ModalProps extends BaseProps, WithChildren {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  size?: 'sm' | 'md' | 'lg' | 'full';
}

/**
 * Props for image display components
 */
export interface ImageDisplayProps extends BaseProps {
  src: string;
  alt: string;
  loading?: 'lazy' | 'eager';
  onLoad?: () => void;
  onError?: () => void;
}

/**
 * Props for layout components
 */
export interface LayoutProps extends BaseProps, WithChildren {
  as?: ElementType;
}
