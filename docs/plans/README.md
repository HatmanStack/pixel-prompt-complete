# Frontend Visual Overhaul: TypeScript + Tailwind Migration

## Overview

This implementation plan covers a complete visual overhaul of the Pixel Prompt frontend, migrating from React JSX with CSS Modules to TypeScript with Tailwind CSS. The goal is to align the UI with the playful, whimsical aesthetic of the reference project (`pixel-prompt-js`) while preserving all existing functionality.

The overhaul includes:
- **Full TypeScript migration** of all 27 JSX files to TSX with proper type definitions
- **Tailwind CSS integration** replacing all CSS Modules with utility-first styling
- **Visual redesign** adopting a dusty rose/muted palette inspired by the reference
- **Interactive elements** including breathing header animation, sound effects, and playful loading states
- **Responsive two-column layout** with gallery on left, generation on right (desktop), and mobile-first single column with gallery toggle

The reference project uses React Native/Expo, so design patterns will be translated to web-appropriate equivalents while maintaining the visual spirit and user experience.

## Prerequisites

Before beginning implementation:

### Development Environment
- Node.js v18+ (v24 LTS preferred)
- npm v9+
- AWS CLI configured with valid credentials
- SAM CLI installed

### Project Dependencies (to be installed in Phase 1)
- TypeScript 5.x
- Tailwind CSS 3.x
- @types/react, @types/react-dom
- Sigmar font (Google Fonts or local asset)

### Recommended Tools
- VS Code with Tailwind CSS IntelliSense extension
- ESLint with TypeScript parser
- Prettier with Tailwind plugin

## Phase Summary

| Phase | Goal | Tasks | Estimated Tokens |
|-------|------|-------|------------------|
| 0 | Foundation: Architecture decisions, deployment specs, testing strategy | N/A (reference doc) | ~15,000 |
| 1 | Infrastructure: TypeScript + Tailwind setup, design tokens, core types | 11 tasks | ~35,000 |
| 2 | Core Components: Layout system, breathing header, sound system | 14 tasks | ~45,000 |
| 3 | Feature Components: Generation panel, image grid, gallery | 16 tasks | ~50,000 |
| 4 | Polish: Animations, accessibility, testing, final integration | 15 tasks | ~35,000 |

**Total: 56 implementation tasks across 4 active phases (~180,000 tokens)**

## Navigation

- [Phase 0: Foundation](./Phase-0.md) - Architecture decisions, patterns, testing strategy
- [Phase 1: Infrastructure](./Phase-1.md) - TypeScript + Tailwind setup, design system
- [Phase 2: Core Components](./Phase-2.md) - Layout, header, sound, base components
- [Phase 3: Feature Components](./Phase-3.md) - Generation, gallery, interactive elements
- [Phase 4: Polish](./Phase-4.md) - Animations, accessibility, testing completion

## Key Design Decisions

1. **Tailwind over CSS-in-JS**: Utility-first approach for rapid iteration and smaller bundle
2. **Full TypeScript**: Complete migration for type safety, not incremental
3. **Zustand for state**: Lightweight alternative to Context for better performance
4. **Web Audio API**: Native browser audio for sound effects (no Expo dependency)
5. **CSS animations**: Prefer CSS/Tailwind animations over JS for performance

## Success Criteria

- [ ] All 27 JSX files converted to TypeScript
- [ ] All CSS Modules replaced with Tailwind classes
- [ ] Visual parity with reference design aesthetic
- [ ] All existing tests passing (updated to TypeScript)
- [ ] Sound effects working on user interaction
- [ ] Breathing header animation functional
- [ ] Two-column responsive layout working
- [ ] Lighthouse accessibility score ≥90
- [ ] No TypeScript errors in strict mode
