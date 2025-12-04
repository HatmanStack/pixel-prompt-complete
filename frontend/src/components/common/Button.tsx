/**
 * Button Component
 * Reusable button with variants, sizes, and sound integration
 */

import type { FC, ReactNode, ButtonHTMLAttributes } from 'react';
import { useSound } from '@/hooks/useSound';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'success';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  fullWidth?: boolean;
  children: ReactNode;
  playClickSound?: boolean;
}

const variantStyles: Record<string, string> = {
  primary: `
    bg-accent text-white
    hover:bg-accent-hover
    disabled:bg-accent/50
  `,
  secondary: `
    bg-secondary text-text border border-primary/30
    hover:bg-primary/50 hover:border-accent
    disabled:bg-secondary/50
  `,
  danger: `
    bg-error text-white
    hover:bg-error/80
    disabled:bg-error/50
  `,
  ghost: `
    bg-transparent text-text-secondary
    hover:bg-secondary hover:text-text
    disabled:text-text-secondary/50
  `,
  success: `
    bg-success text-text-dark
    hover:bg-success/80
    disabled:bg-success/50
  `,
};

const sizeStyles: Record<string, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-base',
  lg: 'px-6 py-3 text-lg',
};

export const Button: FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  fullWidth = false,
  disabled = false,
  children,
  playClickSound = true,
  className = '',
  onClick,
  type = 'button',
  ...props
}) => {
  const { playSound } = useSound();

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (playClickSound && !disabled && !loading) {
      playSound('click');
    }
    onClick?.(e);
  };

  return (
    <button
      type={type}
      disabled={disabled || loading}
      onClick={handleClick}
      className={`
        inline-flex items-center justify-center gap-2
        rounded-md font-medium
        transition-all duration-200
        focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-primary
        disabled:cursor-not-allowed disabled:opacity-60
        motion-reduce:transition-none
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${fullWidth ? 'w-full' : ''}
        ${loading ? 'cursor-wait' : ''}
        ${className}
      `}
      aria-busy={loading}
      {...props}
    >
      {loading && (
        <svg
          className="w-4 h-4 animate-spin motion-reduce:animate-none"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      )}
      {children}
    </button>
  );
};

export default Button;
