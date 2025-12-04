/**
 * Type declarations for JSX modules that haven't been migrated yet
 * This allows TypeScript to import .jsx files without errors
 */

declare module '@/components/generation/GenerationPanel' {
  import type { FC } from 'react';
  const GenerationPanel: FC;
  export default GenerationPanel;
}
