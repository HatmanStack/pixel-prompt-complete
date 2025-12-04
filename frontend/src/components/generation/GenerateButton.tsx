/**
 * GenerateButton Component
 * Main button for triggering image generation, extends base Button
 */

import type { FC } from 'react';
import { Button } from '@/components/common/Button';

interface GenerateButtonProps {
  onClick: () => void;
  isGenerating?: boolean;
  disabled?: boolean;
  label?: string;
  className?: string;
}

export const GenerateButton: FC<GenerateButtonProps> = ({
  onClick,
  isGenerating = false,
  disabled = false,
  label = 'Generate Images',
  className = '',
}) => {
  const buttonText = isGenerating ? 'Generating...' : label;

  return (
    <Button
      variant="primary"
      size="lg"
      loading={isGenerating}
      disabled={disabled}
      onClick={onClick}
      fullWidth
      className={`
        min-h-14
        bg-gradient-to-br from-accent to-button
        hover:from-accent-hover hover:to-button/80
        shadow-md hover:shadow-lg hover:-translate-y-0.5
        active:translate-y-0 active:shadow-sm
        transition-all duration-200
        motion-reduce:transform-none motion-reduce:transition-none
        ${isGenerating ? 'from-button to-accent animate-pulse motion-reduce:animate-none' : ''}
        ${className}
      `}
      aria-label={buttonText}
    >
      {buttonText}
    </Button>
  );
};

export default GenerateButton;
