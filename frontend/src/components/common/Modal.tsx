/**
 * Modal Component
 * Reusable modal dialog with overlay, focus trap, and keyboard navigation
 */

import { useEffect, useRef, type FC, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useSound } from '@/hooks/useSound';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  title?: string;
  ariaLabel?: string;
  size?: 'sm' | 'md' | 'lg' | 'full';
  className?: string;
}

const sizeStyles: Record<string, string> = {
  sm: 'max-w-md',
  md: 'max-w-2xl',
  lg: 'max-w-4xl',
  full: 'max-w-[95vw] w-full',
};

export const Modal: FC<ModalProps> = ({
  isOpen,
  onClose,
  children,
  title,
  ariaLabel = 'Modal dialog',
  size = 'md',
  className = '',
}) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);
  const { playSound } = useSound();

  // Play expand sound when modal opens
  useEffect(() => {
    if (isOpen) {
      playSound('expand');
    }
  }, [isOpen, playSound]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      previousActiveElement.current = document.activeElement as HTMLElement;
      document.body.style.overflow = 'hidden';

      // Focus the modal
      setTimeout(() => {
        modalRef.current?.focus();
      }, 0);

      return () => {
        document.body.style.overflow = 'unset';
        // Return focus to previous element
        previousActiveElement.current?.focus();
      };
    }
  }, [isOpen]);

  // Handle Escape key to close modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => {
        document.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [isOpen, onClose]);

  // Focus trap
  useEffect(() => {
    if (!isOpen || !modalRef.current) return;

    const modal = modalRef.current;
    const focusableElements = modal.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    const handleTabKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    modal.addEventListener('keydown', handleTabKey);
    return () => {
      modal.removeEventListener('keydown', handleTabKey);
    };
  }, [isOpen]);

  if (!isOpen) {
    return null;
  }

  const modalContent = (
    <div
      className="
        fixed inset-0 z-50
        flex items-center justify-center
        bg-black/85
        p-4 md:p-6
        animate-[fadeIn_200ms_ease-out]
      "
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      aria-labelledby={title ? 'modal-title' : undefined}
    >
      <div
        ref={modalRef}
        tabIndex={-1}
        className={`
          relative
          bg-secondary rounded-lg
          max-h-[95vh] overflow-auto
          shadow-2xl
          animate-[slideUp_300ms_ease-out]
          focus:outline-none
          motion-reduce:animate-none
          ${sizeStyles[size]}
          ${className}
        `}
        onClick={(e) => e.stopPropagation()}
        role="document"
      >
        {/* Close button */}
        <button
          className="
            absolute top-3 right-3 z-10
            flex items-center justify-center
            w-9 h-9 rounded-full
            bg-black/50 text-white text-lg
            hover:bg-black/70 hover:scale-110
            focus:outline-none focus:ring-2 focus:ring-accent
            transition-all duration-200
            motion-reduce:transform-none motion-reduce:transition-none
          "
          onClick={onClose}
          aria-label="Close modal"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
            className="w-5 h-5"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>

        {/* Title */}
        {title && (
          <h2
            id="modal-title"
            className="
              px-6 pt-6 pb-2
              text-xl font-display text-accent
            "
          >
            {title}
          </h2>
        )}

        {/* Content */}
        <div className={title ? 'px-6 pb-6' : 'p-6'}>{children}</div>
      </div>
    </div>
  );

  // Use portal to render at document body level
  return createPortal(modalContent, document.body);
};

export default Modal;
