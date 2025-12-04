/**
 * PromptEnhancer Component
 * UI for prompt enhancement feature
 * Supports Ctrl+E keyboard shortcut
 */

import { useState, useEffect, useCallback, type FC } from 'react';
import { enhancePrompt } from '@/api/client';
import { useAppStore } from '@/stores/useAppStore';
import { useToast } from '@/stores/useToastStore';
import { useSound } from '@/hooks/useSound';

interface EnhancedPromptData {
  short: string;
  long: string;
  original: string;
}

interface PromptEnhancerProps {
  disabled?: boolean;
}

export const PromptEnhancer: FC<PromptEnhancerProps> = ({ disabled = false }) => {
  const { prompt, setPrompt } = useAppStore();
  const { error: showErrorToast } = useToast();
  const { playSound } = useSound();

  const [isEnhancing, setIsEnhancing] = useState(false);
  const [enhancedPrompt, setEnhancedPrompt] = useState<EnhancedPromptData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showLong, setShowLong] = useState(false);

  // Shared enhancement logic
  const runEnhance = useCallback(async () => {
    setIsEnhancing(true);
    setError(null);
    setEnhancedPrompt(null);

    try {
      const response = await enhancePrompt(prompt);

      if (response.short_prompt || response.long_prompt) {
        setEnhancedPrompt({
          short: response.short_prompt || prompt,
          long: response.long_prompt || response.short_prompt || prompt,
          original: prompt,
        });
        playSound('swoosh');
      } else {
        throw new Error('No enhanced prompt received');
      }
    } catch (err) {
      console.error('Enhancement error:', err);
      const message = err instanceof Error ? err.message : 'Failed to enhance prompt';
      setError(message);
      showErrorToast(message);
    } finally {
      setIsEnhancing(false);
    }
  }, [prompt, playSound, showErrorToast]);

  // Listen for keyboard shortcut (Ctrl+E)
  useEffect(() => {
    const handleEnhancePromptTrigger = async () => {
      if (!disabled && !isEnhancing && prompt.trim()) {
        await runEnhance();
      }
    };

    document.addEventListener('enhance-prompt-trigger', handleEnhancePromptTrigger);
    return () => {
      document.removeEventListener('enhance-prompt-trigger', handleEnhancePromptTrigger);
    };
  }, [disabled, isEnhancing, prompt, runEnhance]);

  const handleEnhance = async () => {
    if (!prompt.trim()) {
      setError('Please enter a prompt first');
      return;
    }
    await runEnhance();
  };

  const handleUse = () => {
    if (!enhancedPrompt) return;
    const promptToUse = showLong ? enhancedPrompt.long : enhancedPrompt.short;
    setPrompt(promptToUse);
    playSound('switch');
    setEnhancedPrompt(null);
  };

  const handleDiscard = () => {
    playSound('click');
    setEnhancedPrompt(null);
    setError(null);
  };

  return (
    <div className="flex w-full flex-col gap-2">
      {!enhancedPrompt ? (
        <button
          className="
            inline-flex items-center justify-center gap-2
            px-6 py-2
            text-sm font-medium
            text-text bg-secondary
            border border-accent/50 rounded-md
            cursor-pointer
            transition-all duration-150
            hover:bg-secondary/80 hover:border-accent
            disabled:opacity-50 disabled:cursor-not-allowed
          "
          onClick={handleEnhance}
          disabled={disabled || isEnhancing || !prompt.trim()}
          type="button"
        >
          {isEnhancing ? (
            <>
              <span className="w-4 h-4 border-2 border-secondary border-t-accent rounded-full animate-spin" />
              <span>Enhancing...</span>
            </>
          ) : (
            <>
              <span className="text-lg">✨</span>
              <span>Enhance Prompt</span>
            </>
          )}
        </button>
      ) : (
        <div
          className="
            flex flex-col gap-4 p-4
            bg-secondary border border-accent rounded-lg
            animate-in slide-in-from-top-2 duration-200
          "
        >
          <div className="flex justify-between items-center gap-4 flex-col md:flex-row md:items-center">
            <h4 className="m-0 text-base text-text font-medium">Enhanced Prompt</h4>
            <div className="flex gap-0.5 bg-primary/20 rounded-md p-0.5 self-stretch md:self-auto">
              <button
                className={`
                  flex-1 md:flex-initial px-4 py-1
                  text-xs font-medium
                  border-none rounded-sm
                  cursor-pointer
                  transition-all duration-150
                  ${!showLong
                    ? 'text-text bg-accent'
                    : 'text-text-secondary bg-transparent hover:text-text'
                  }
                `}
                onClick={() => setShowLong(false)}
                type="button"
              >
                Short
              </button>
              <button
                className={`
                  flex-1 md:flex-initial px-4 py-1
                  text-xs font-medium
                  border-none rounded-sm
                  cursor-pointer
                  transition-all duration-150
                  ${showLong
                    ? 'text-text bg-accent'
                    : 'text-text-secondary bg-transparent hover:text-text'
                  }
                `}
                onClick={() => setShowLong(true)}
                type="button"
              >
                Long
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                Original:
              </label>
              <p className="text-sm leading-relaxed text-text p-3 bg-primary/30 rounded-sm m-0">
                {enhancedPrompt.original}
              </p>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                Enhanced:
              </label>
              <p className="text-sm leading-relaxed text-accent font-medium p-3 bg-primary/30 rounded-sm m-0">
                {showLong ? enhancedPrompt.long : enhancedPrompt.short}
              </p>
            </div>
          </div>

          <div className="flex gap-2 flex-col md:flex-row">
            <button
              className="
                flex-1 py-2 px-4
                text-sm font-semibold
                text-white bg-accent
                border-none rounded-md
                cursor-pointer
                transition-all duration-150
                hover:bg-accent-hover hover:-translate-y-0.5 hover:shadow-md
              "
              onClick={handleUse}
              type="button"
            >
              Use This
            </button>
            <button
              className="
                flex-1 py-2 px-4
                text-sm font-semibold
                text-text-secondary bg-secondary
                border-none rounded-md
                cursor-pointer
                transition-all duration-150
                hover:text-text hover:bg-primary/50
              "
              onClick={handleDiscard}
              type="button"
            >
              Discard
            </button>
          </div>
        </div>
      )}

      {error && (
        <div
          className="
            flex items-center gap-2 p-2
            text-sm text-error
            bg-error/10 border border-error rounded-sm
          "
        >
          <span className="text-base">⚠</span>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
};

export default PromptEnhancer;
