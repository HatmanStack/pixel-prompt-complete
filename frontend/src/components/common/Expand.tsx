/**
 * Expand Component
 * Collapsible section with smooth animation and sound
 */

import { useState, useRef, useEffect, useId, type FC, type ReactNode } from 'react';
import { useSound } from '@/hooks/useSound';

interface ExpandProps {
  title: string;
  children: ReactNode;
  defaultExpanded?: boolean;
  onToggle?: (isExpanded: boolean) => void;
  className?: string;
}

export const Expand: FC<ExpandProps> = ({
  title,
  children,
  defaultExpanded = false,
  onToggle,
  className = '',
}) => {
  const uniqueId = useId();
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [height, setHeight] = useState<string | number>(defaultExpanded ? 'auto' : 0);
  const contentRef = useRef<HTMLDivElement>(null);
  const { playSound } = useSound();

  // Update height when expanded state changes
  useEffect(() => {
    if (!contentRef.current) return;

    if (isExpanded) {
      const scrollHeight = contentRef.current.scrollHeight;
      setHeight(scrollHeight);

      // After animation, set to auto for dynamic content
      const timer = setTimeout(() => {
        setHeight('auto');
      }, 300);

      return () => clearTimeout(timer);
    } else {
      // Set to current height first, then to 0 for smooth collapse
      const scrollHeight = contentRef.current.scrollHeight;
      setHeight(scrollHeight);

      // Force reflow then collapse
      const timer = setTimeout(() => {
        setHeight(0);
      }, 10);

      return () => clearTimeout(timer);
    }
  }, [isExpanded]);

  const handleToggle = () => {
    const newState = !isExpanded;
    setIsExpanded(newState);
    playSound('expand');
    onToggle?.(newState);
  };

  return (
    <div className={`rounded-lg overflow-hidden ${className}`}>
      <button
        className="
          w-full flex items-center justify-between
          px-4 py-3
          bg-secondary text-text
          hover:bg-primary/50
          focus:outline-none focus:ring-2 focus:ring-accent focus:ring-inset
          transition-colors
        "
        onClick={handleToggle}
        aria-expanded={isExpanded}
        aria-controls={uniqueId}
        type="button"
      >
        <span className="font-medium">{title}</span>
        <span
          className={`
            transition-transform duration-300
            motion-reduce:transition-none
            ${isExpanded ? 'rotate-180' : 'rotate-0'}
          `}
          aria-hidden="true"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
            className="w-5 h-5"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19.5 8.25l-7.5 7.5-7.5-7.5"
            />
          </svg>
        </span>
      </button>

      <div
        ref={contentRef}
        id={uniqueId}
        className="
          overflow-hidden
          transition-[height] duration-300 ease-in-out
          motion-reduce:transition-none
        "
        style={{ height: typeof height === 'number' ? `${height}px` : height }}
        aria-hidden={!isExpanded}
      >
        <div className="p-4 bg-primary/30">{children}</div>
      </div>
    </div>
  );
};

export default Expand;
