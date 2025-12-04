/**
 * Container Component
 * Wrapper component with max-width and responsive padding
 */

import type { FC, ReactNode, ElementType } from 'react';

interface ContainerProps {
  children: ReactNode;
  as?: ElementType;
  className?: string;
  fullWidth?: boolean;
}

export const Container: FC<ContainerProps> = ({
  children,
  as: Component = 'div',
  className = '',
  fullWidth = false,
}) => {
  return (
    <Component
      className={`
        w-full
        ${fullWidth ? '' : 'max-w-7xl mx-auto'}
        px-4 sm:px-6 lg:px-8
        ${className}
      `}
    >
      {children}
    </Component>
  );
};

export default Container;
