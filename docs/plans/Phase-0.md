# Phase 0: Foundation

This phase establishes the architectural foundation that applies to ALL subsequent phases. Engineers should read and internalize this document before beginning any implementation work.

## Architecture Decision Records (ADRs)

### ADR-001: TypeScript Migration Strategy

**Context**: The frontend currently uses JavaScript with JSX. We need type safety for maintainability.

**Decision**: Full migration to TypeScript with strict mode enabled.

**Rationale**:
- Strict mode catches more bugs at compile time
- Full migration avoids mixed codebase confusion
- Better IDE support and autocomplete
- Easier refactoring with type information

**Consequences**:
- All `.jsx` files become `.tsx`
- All `.js` utility files become `.ts`
- Must define types for all props, state, and API responses
- Test files also migrated to TypeScript

---

### ADR-002: Styling Approach - Tailwind CSS

**Context**: Current project uses CSS Modules. Reference uses React Native StyleSheet.

**Decision**: Adopt Tailwind CSS with a custom theme configuration.

**Rationale**:
- Utility-first enables rapid prototyping
- Custom theme allows design token consistency
- Smaller bundle than CSS-in-JS solutions
- Excellent developer experience with IntelliSense
- Easy to match reference design with custom colors

**Consequences**:
- Remove all `.module.css` files after migration
- Configure `tailwind.config.ts` with design tokens from reference
- Use `@apply` sparingly for truly reusable patterns
- Prefer inline utilities over abstracted classes

---

### ADR-003: State Management - Zustand

**Context**: Current project uses React Context. Reference uses Zustand.

**Decision**: Migrate to Zustand for global state management.

**Rationale**:
- Simpler API than Context + useReducer
- Better performance (no provider wrapper re-renders)
- Matches reference project pattern
- Excellent TypeScript support
- Tiny bundle size (~1KB)

**Consequences**:
- Create stores in `src/stores/` directory
- Remove Context providers from component tree
- Use selectors to prevent unnecessary re-renders
- Maintain hooks pattern for consuming state

---

### ADR-004: Sound System - Web Audio API

**Context**: Reference uses Expo Audio (React Native). We need browser-compatible audio.

**Decision**: Use HTML5 Audio with a custom hook abstraction.

**Rationale**:
- No additional dependencies
- Works across all modern browsers
- Can preload sounds for instant playback
- Simple API wrappable in React hook

**Consequences**:
- Create `useSound` hook (already exists, needs update)
- Preload sounds on app initialization
- Handle user interaction requirement for audio playback
- Provide mute/unmute global control

---

### ADR-005: Animation Strategy

**Context**: Reference uses React Native Animated API. We need web-compatible animations.

**Decision**: Use CSS animations with Tailwind + minimal JS for complex sequences.

**Rationale**:
- CSS animations are GPU-accelerated
- Tailwind has built-in animation utilities
- Reduces JavaScript bundle
- Easier to maintain than JS animation libraries

**Consequences**:
- Define custom animations in `tailwind.config.ts`
- Use `@keyframes` for breathing animation
- Framer Motion optional for complex orchestration
- Respect `prefers-reduced-motion` media query

---

### ADR-006: Responsive Layout Strategy

**Context**: Reference has separate Desktop/Mobile layout components. Current uses CSS media queries.

**Decision**: Tailwind responsive prefixes with layout components for structural differences.

**Rationale**:
- Tailwind's responsive system is intuitive (`md:`, `lg:`)
- Layout components only when DOM structure differs significantly
- Avoid duplicating component logic
- Single source of truth for component behavior

**Consequences**:
- Create `<ResponsiveLayout>` component
- Use Tailwind breakpoints: `sm` (640px), `md` (768px), `lg` (1024px)
- Desktop: Two-column (gallery left, generation right)
- Mobile: Single column with gallery toggle/drawer

---

## Design System Specification

### Color Palette (Inspired by Reference)

```typescript
// Tailwind theme extension
colors: {
  // Primary backgrounds
  primary: '#25292e',      // Main dark background
  secondary: '#3a3c3f',    // Elevated surfaces

  // Accent colors
  accent: {
    DEFAULT: '#B58392',    // Dusty rose - primary accent
    hover: '#C99AAB',      // Lighter for hover states
    muted: '#958DA5',      // Muted purple - secondary accent
  },

  // Text
  text: {
    DEFAULT: '#FFFFFF',
    secondary: '#CCCCCC',
    dark: '#000000',
  },

  // Interactive
  button: {
    DEFAULT: '#958DA5',
    pressed: '#7A7085',
    success: '#9DA58D',
    danger: '#FF6B6B',
  },

  // Semantic
  success: '#9DA58D',
  error: '#FF6B6B',
  warning: '#FFB347',
  info: '#87CEEB',
}
```

### Typography

```typescript
// Tailwind theme extension
fontFamily: {
  display: ['Sigmar', 'cursive'],  // Headers, breathing animation
  body: ['system-ui', 'sans-serif'], // Body text
}

fontSize: {
  xs: '0.875rem',    // 14px
  sm: '1rem',        // 16px
  base: '1.125rem',  // 18px
  lg: '1.25rem',     // 20px
  xl: '1.5rem',      // 24px
  '2xl': '2rem',     // 32px
}
```

### Spacing Scale

Use Tailwind's default spacing scale with these semantic additions:

```typescript
spacing: {
  container: '1rem',      // Standard container padding
  section: '2rem',        // Between major sections
  element: '0.5rem',      // Between related elements
}
```

### Border Radius

```typescript
borderRadius: {
  sm: '0.25rem',   // 4px - buttons, inputs
  md: '0.5rem',    // 8px - cards
  lg: '1rem',      // 16px - modals, large cards
  full: '9999px',  // Pills, avatars
}
```

---

## Deployment Script Specification

### Overview

The `npm run deploy` command executes `backend/scripts/deploy.js` which handles:
1. Interactive prompting for configuration (with saved defaults)
2. S3 deployment bucket creation
3. SAM build and deploy
4. Frontend `.env` file generation

### Deployment Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    npm run deploy                            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Check Prerequisites                                      │
│     - AWS CLI configured?                                    │
│     - SAM CLI installed?                                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Load Saved Configuration                                 │
│     - Read .deploy-config.json if exists                     │
│     - Use values as defaults for prompts                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Interactive Prompts (ALWAYS)                             │
│     - AWS Region [saved default]                             │
│     - Stack Name [saved default]                             │
│     - Prompt Model: Provider, ID, API Key                    │
│     - Image Models: Count, Provider, ID, API Key each        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Save Configuration                                       │
│     - Write to .deploy-config.json (git-ignored)             │
│     - Validate configuration                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  5. SAM Build                                                │
│     - Run sam build in backend directory                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Ensure Deployment Bucket                                 │
│     - Check if sam-deploy-{stackName}-{region} exists        │
│     - Create if missing                                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  7. SAM Deploy                                               │
│     - Use --s3-bucket (NOT --resolve-s3)                     │
│     - Pass parameter overrides programmatically              │
│     - --no-confirm-changeset                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  8. Capture Stack Outputs                                    │
│     - Query CloudFormation for outputs                       │
│     - Extract: ApiEndpoint, CloudFrontDomain, S3BucketName   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  9. Update Frontend .env                                     │
│     - Write VITE_API_ENDPOINT                                │
│     - Write VITE_CLOUDFRONT_DOMAIN                           │
│     - Write VITE_S3_BUCKET                                   │
│     - Write VITE_ENVIRONMENT                                 │
└─────────────────────────────────────────────────────────────┘
```

### Configuration Files

**`.deploy-config.json`** (git-ignored):
```json
{
  "region": "us-west-2",
  "stackName": "pixel-prompt-dev",
  "lambdaMemory": "3008",
  "lambdaTimeout": "900",
  "globalRateLimit": "1000",
  "ipRateLimit": "100",
  "s3RetentionDays": "30",
  "promptModel": {
    "provider": "openai",
    "id": "gpt-4o",
    "apiKey": "sk-..."
  },
  "models": [
    {
      "provider": "openai",
      "id": "gpt-image-1",
      "apiKey": "sk-..."
    }
  ]
}
```

**`samconfig.toml`** (minimal, generated values override):
```toml
version = 0.1
[default.deploy.parameters]
stack_name = "pixel-prompt-dev"
region = "us-west-2"
capabilities = "CAPABILITY_IAM"
```

---

## Testing Strategy

### Testing Philosophy

1. **Unit Tests**: Test individual components and functions in isolation
2. **Integration Tests**: Test component interactions with mocked APIs
3. **No E2E in CI**: End-to-end tests require live AWS resources, run locally only

### Test File Organization

```
frontend/
├── tests/
│   ├── setupTests.ts           # Test setup, mocks, global config
│   ├── __tests__/
│   │   ├── components/         # Component unit tests
│   │   │   ├── Header.test.tsx
│   │   │   ├── GenerateButton.test.tsx
│   │   │   └── ...
│   │   ├── hooks/              # Hook tests
│   │   │   ├── useSound.test.ts
│   │   │   └── useJobPolling.test.ts
│   │   ├── stores/             # Zustand store tests
│   │   │   ├── useAppStore.test.ts
│   │   │   └── useUIStore.test.ts
│   │   ├── integration/        # Multi-component integration
│   │   │   ├── generateFlow.test.tsx
│   │   │   └── galleryFlow.test.tsx
│   │   └── utils/              # Utility function tests
│   └── fixtures/               # Test data
│       └── apiResponses.ts
```

### Mocking Strategy

**API Mocking**: Use `vitest` mocks or `msw` (Mock Service Worker) for API calls.

```typescript
// Example: Mocking fetch
vi.mock('../api/client', () => ({
  apiClient: {
    generate: vi.fn().mockResolvedValue({ jobId: 'test-123' }),
    getStatus: vi.fn().mockResolvedValue({ status: 'completed', images: [] }),
  }
}));
```

**Sound Mocking**: Mock the Audio API for sound tests.

```typescript
// setupTests.ts
global.Audio = vi.fn().mockImplementation(() => ({
  play: vi.fn().mockResolvedValue(undefined),
  pause: vi.fn(),
  load: vi.fn(),
}));
```

**Store Mocking**: Use Zustand's testing utilities.

```typescript
import { useAppStore } from '../stores/useAppStore';

beforeEach(() => {
  useAppStore.setState({ prompt: '', images: [] });
});
```

### CI Pipeline Configuration

Tests run in GitHub Actions with:
- Node.js 20.x
- `npm ci` for reproducible installs
- `npm run lint` for code quality
- `npm test` for unit + integration tests with coverage
- **No deployment** - CI is test-only

```yaml
# .github/workflows/test.yml (excerpt)
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci
      - run: npm run lint
      - run: npm test -- --coverage
```

### Coverage Requirements

- Statements: ≥80%
- Branches: ≥75%
- Functions: ≥80%
- Lines: ≥80%

---

## Shared Patterns and Conventions

### File Naming

- Components: `PascalCase.tsx` (e.g., `GenerateButton.tsx`)
- Hooks: `camelCase.ts` with `use` prefix (e.g., `useSound.ts`)
- Stores: `camelCase.ts` with `use` prefix (e.g., `useAppStore.ts`)
- Types: `camelCase.types.ts` or inline in component
- Utils: `camelCase.ts` (e.g., `imageHelpers.ts`)

### Component Structure

```typescript
// Standard component template
import { type FC } from 'react';

interface ComponentNameProps {
  required: string;
  optional?: number;
  onAction?: () => void;
}

export const ComponentName: FC<ComponentNameProps> = ({
  required,
  optional = 10,
  onAction,
}) => {
  // Hooks first
  // Derived state
  // Event handlers
  // Render

  return (
    <div className="...">
      {/* JSX */}
    </div>
  );
};
```

### Tailwind Class Ordering

Follow this order for consistency:
1. Layout (display, position, flex, grid)
2. Sizing (width, height, padding, margin)
3. Typography (font, text)
4. Visual (background, border, shadow)
5. Interactive (hover, focus, transition)

```tsx
// Example
<button className="
  flex items-center justify-center
  px-6 py-3
  font-display text-lg text-white
  bg-accent rounded-md shadow-md
  hover:bg-accent-hover focus:ring-2 transition-colors
">
```

### Import Organization

```typescript
// 1. React and external libraries
import { useState, useEffect, type FC } from 'react';
import { useStore } from 'zustand';

// 2. Internal absolute imports (@/)
import { useAppStore } from '@/stores/useAppStore';
import { apiClient } from '@/api/client';

// 3. Relative imports (components, utils)
import { Button } from './Button';
import { formatDate } from '../utils/date';

// 4. Types (if separate file)
import type { GenerateResponse } from '@/types/api';

// 5. Assets
import clickSound from '@/assets/sounds/click.wav';
```

### Error Handling Pattern

```typescript
// Use error boundaries for component errors
// Use try-catch for async operations
// Display user-friendly messages via toast

try {
  const result = await apiClient.generate(prompt);
  // success handling
} catch (error) {
  const message = error instanceof Error
    ? error.message
    : 'An unexpected error occurred';
  toast.error(message);
}
```

### Accessibility Requirements

- All interactive elements must be keyboard accessible
- Use semantic HTML (`button`, `nav`, `main`, `section`)
- Provide `aria-label` for icon-only buttons
- Respect `prefers-reduced-motion` for animations
- Maintain color contrast ratio ≥4.5:1
- Test with screen reader (VoiceOver/NVDA)

---

## Commit Message Format

All commits must follow conventional commits format:

```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

type(scope): brief description

Detail 1
Detail 2
```

**Important**: Do NOT include Co-Authored-By, Generated-By, or similar attribution lines in commit messages.

### Types
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `style`: Code style changes (formatting, semicolons)
- `test`: Adding or updating tests
- `docs`: Documentation changes
- `chore`: Build process, dependencies, tooling

### Scopes (Frontend)
- `ui`: Visual/styling changes
- `components`: Component changes
- `hooks`: Custom hooks
- `stores`: State management
- `api`: API client changes
- `types`: TypeScript types
- `config`: Configuration files
- `test`: Test files

### Examples
```
feat(ui): add breathing header animation

Implement CSS keyframe animation for header text
Add responsive sizing for mobile/desktop
```

```
refactor(components): convert GenerateButton to TypeScript

Add prop types interface
Replace CSS Modules with Tailwind classes
Update tests to use .tsx extension
```
