/**
 * PromptInput Component
 * Textarea input for entering image generation prompts
 * Styled with Tailwind, integrated with Zustand store
 */

import { useRef, useEffect, type FC, type ChangeEvent, type KeyboardEvent } from 'react';
import { useAppStore } from '@/stores/useAppStore';
import { useSound } from '@/hooks/useSound';

interface PromptInputProps {
  maxLength?: number;
  placeholder?: string;
  disabled?: boolean;
}

export const PromptInput: FC<PromptInputProps> = ({
  maxLength = 500,
  placeholder = 'Describe the image you want to generate...',
  disabled = false,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { prompt, setPrompt } = useAppStore();
  const { playSound } = useSound();

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [prompt]);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;

    // Enforce max length
    if (newValue.length <= maxLength) {
      setPrompt(newValue);
    }
  };

  const handleClear = () => {
    // Confirm before clearing if prompt is long
    if (prompt.length > 50) {
      if (!window.confirm('Are you sure you want to clear this prompt?')) {
        return;
      }
    }
    playSound('switch');
    setPrompt('');
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Escape key: Clear input
    if (e.key === 'Escape') {
      handleClear();
    }

    // Ctrl/Cmd + Enter: Trigger generation (handled by parent)
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      // Dispatch custom event that parent can listen to
      const event = new CustomEvent('generate-trigger');
      document.dispatchEvent(event);
    }
  };

  const remainingChars = maxLength - prompt.length;
  const isNearLimit = remainingChars < 50;

  return (
    <div className="flex w-full flex-col gap-2">
      <label htmlFor="prompt-input" className="sr-only">
        Image prompt
      </label>
      <div className="relative w-full">
        <textarea
          ref={textareaRef}
          id="prompt-input"
          className="
            w-full min-h-[120px] max-h-[300px]
            p-4 pr-12
            font-body text-base leading-relaxed
            text-text bg-secondary
            border-[3px] border-accent rounded-lg
            resize-none
            transition-colors duration-150
            placeholder:text-text-secondary/60
            focus:outline-none focus:border-accent-hover focus:bg-secondary/80
            disabled:opacity-60 disabled:cursor-not-allowed
            md:min-h-[140px]
          "
          value={prompt}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={3}
          aria-describedby="prompt-hint"
        />

        {prompt && !disabled && (
          <button
            className="
              absolute top-4 right-4
              w-7 h-7
              flex items-center justify-center
              bg-secondary text-text-secondary
              border-none rounded-full
              cursor-pointer text-lg
              transition-all duration-150
              hover:bg-error hover:text-white hover:scale-110
              active:scale-95
            "
            onClick={handleClear}
            aria-label="Clear prompt"
            type="button"
          >
            ✕
          </button>
        )}
      </div>

      <div className="flex justify-between items-center gap-4 px-1">
        <span
          className={`
            text-sm tabular-nums
            ${isNearLimit ? 'text-warning font-medium' : 'text-text-secondary'}
          `}
          aria-live="polite"
        >
          {prompt.length} / {maxLength}
        </span>

        <span id="prompt-hint" className="text-xs text-text-secondary/70 text-right hidden md:block">
          Press Ctrl+Enter to generate • Esc to clear
        </span>
      </div>
    </div>
  );
};

export default PromptInput;
