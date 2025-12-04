# Phase 2: Core Components

## Phase Goal

Migrate core structural components to TypeScript with Tailwind styling. This phase focuses on the layout system, header with breathing animation, sound system, and base UI components that other features depend on.

**Success Criteria:**
- Responsive two-column layout working (desktop) with single-column mobile
- Breathing "PIXEL PROMPT" header animation functional
- Sound system playing effects on interactions
- Base UI components (Button, Modal, Toast) converted and styled
- All migrated components pass TypeScript strict mode

**Estimated Tokens:** ~40,000

---

## Prerequisites

- Phase 1 complete (TypeScript, Tailwind, Zustand configured)
- Design tokens in tailwind.config.ts
- Sound files in public/sounds/
- Core types defined

---

## Tasks

### Task 1: Create Responsive Layout Component

**Goal:** Build the two-column desktop / single-column mobile layout structure.

**Files to Modify/Create:**
- `frontend/src/components/layout/ResponsiveLayout.tsx` - Main layout wrapper
- `frontend/src/components/layout/DesktopLayout.tsx` - Two-column layout
- `frontend/src/components/layout/MobileLayout.tsx` - Single-column layout
- `frontend/src/components/layout/index.ts` - Re-export layouts
- `frontend/src/hooks/useBreakpoint.ts` - Responsive breakpoint hook

**Prerequisites:**
- Tailwind configured with breakpoints

**Implementation Steps:**
- Create useBreakpoint hook that returns current breakpoint (sm, md, lg, xl)
- Use window.matchMedia for efficient breakpoint detection
- Create DesktopLayout with left (gallery) and right (generation) columns
- Create MobileLayout with single column and gallery toggle state
- Create ResponsiveLayout that conditionally renders Desktop or Mobile
- Use Tailwind's responsive utilities where possible, JS only for structural changes
- Match reference project's column proportions (roughly 50/50 or gallery slightly narrower)

**Verification Checklist:**
- [ ] Desktop (≥1024px) shows two-column layout
- [ ] Mobile (<1024px) shows single-column layout
- [ ] Layout transition is smooth (no jarring reflows)
- [ ] useBreakpoint hook updates on resize
- [ ] TypeScript types for props are complete

**Testing Instructions:**
- Unit test useBreakpoint hook with mocked matchMedia
- Test ResponsiveLayout renders correct child based on breakpoint
- Manual test: resize browser and verify layout switches

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(components): add responsive layout system

Create DesktopLayout with two-column grid
Create MobileLayout with single column
Add useBreakpoint hook for responsive detection
```

---

### Task 2: Create Breathing Header Component

**Goal:** Implement the animated "PIXEL PROMPT" header with breathing text effect, replacing the existing BreathingBackground component.

**Files to Modify/Create:**
- `frontend/src/components/common/BreathingHeader.tsx` - **New component** (replaces BreathingBackground)
- `frontend/tailwind.config.ts` - Add breathing animation keyframes
- Delete: `frontend/src/components/common/BreathingBackground.jsx` - Old implementation being replaced
- Delete: `frontend/src/components/common/BreathingBackground.module.css` - Old styles

**Note:** This is a reimplementation, not a direct migration. The new BreathingHeader uses CSS animations instead of the previous approach, inspired by the reference project's Breathing.js component.

**Prerequisites:**
- Sigmar font loaded
- Tailwind custom animations configured

**Implementation Steps:**
- Study reference Breathing.js component animation pattern
- Create CSS keyframes for the breathing effect (scale + opacity changes)
- Each letter should animate independently with staggered delays
- Implement using CSS animations (more performant than JS)
- Use Tailwind's animation utilities with custom keyframes
- Make responsive (larger text on desktop, smaller on mobile)
- Respect prefers-reduced-motion by disabling animation

**Verification Checklist:**
- [ ] All 12 characters animate independently
- [ ] Animation is smooth at 60fps
- [ ] Font is Sigmar with correct styling
- [ ] Responsive sizing works (smaller on mobile)
- [ ] Animation stops with prefers-reduced-motion

**Testing Instructions:**
- Unit test component renders all characters
- Test that animation classes are applied
- Manual test: verify visual animation matches reference
- Test reduced motion preference in browser settings

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(components): add breathing header animation

Implement animated PIXEL PROMPT header
Use CSS keyframes with staggered delays
Add responsive sizing and reduced motion support
```

---

### Task 3: Migrate Sound Hook and System

**Goal:** Update the useSound hook for the new architecture and ensure sounds play correctly.

**Files to Modify/Create:**
- `frontend/src/hooks/useSound.ts` - Updated sound hook
- `frontend/src/stores/useUIStore.ts` - Add sound muted state
- `frontend/src/components/common/SoundToggle.tsx` - Mute/unmute button

**Prerequisites:**
- Sound files in public/sounds/
- Zustand stores created

**Implementation Steps:**
- Refactor useSound hook to TypeScript with proper types
- Preload sounds on first user interaction (browser audio policy)
- Add sound types: 'click', 'swoosh', 'switch', 'expand'
- Integrate with useUIStore for global mute state
- Handle audio playback errors gracefully
- Create SoundToggle component for user control
- Ensure sounds don't overlap (stop previous before playing new)

**Verification Checklist:**
- [ ] Each sound type plays correct audio file
- [ ] Sounds preload after first user interaction
- [ ] Mute toggle works globally
- [ ] No console errors during playback
- [ ] Sounds work across browsers (Chrome, Firefox, Safari)

**Testing Instructions:**
- Unit test useSound with mocked Audio API
- Test mute state persists correctly
- Manual test: trigger each sound type and verify playback

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(hooks): migrate useSound to TypeScript

Add typed sound effects system
Integrate with UI store for mute state
Add SoundToggle component
```

---

### Task 4: Migrate Header Component

**Goal:** Convert the existing Header to TypeScript with Tailwind, integrating breathing animation.

**Files to Modify/Create:**
- `frontend/src/components/common/Header.tsx` - Rename and convert
- Delete: `frontend/src/components/common/Header.jsx`
- Delete: `frontend/src/components/common/Header.module.css`

**Prerequisites:**
- BreathingHeader component created
- SoundToggle component created

**Implementation Steps:**
- Convert Header.jsx to Header.tsx
- Replace CSS Module classes with Tailwind utilities
- Integrate BreathingHeader as the main title element
- Add SoundToggle to header bar
- Style to match reference project aesthetic (dark background, accent borders)
- Ensure proper semantic HTML (header, nav elements)
- Make responsive with Tailwind breakpoints

**Verification Checklist:**
- [ ] Header renders without TypeScript errors
- [ ] Breathing animation displays correctly
- [ ] Sound toggle visible and functional
- [ ] Styling matches playful aesthetic
- [ ] Responsive behavior correct

**Testing Instructions:**
- Unit test Header renders children correctly
- Test integration with BreathingHeader
- Manual test: verify visual appearance matches design

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate Header to TypeScript

Convert Header component to TSX
Replace CSS Modules with Tailwind
Integrate breathing animation and sound toggle
```

---

### Task 5: Create Button Component and Migrate GenerateButton

**Goal:** Create a new reusable Button component with Tailwind styling and sound integration, then migrate GenerateButton to use it.

**Files to Modify/Create:**
- `frontend/src/components/common/Button.tsx` - **New component** (no existing Button.jsx)
- `frontend/src/components/generation/GenerateButton.tsx` - Rename and convert
- Delete: `frontend/src/components/generation/GenerateButton.jsx`
- Delete: `frontend/src/components/generation/GenerateButton.module.css`

**Note:** Button.tsx is a new shared component. There is no existing Button.jsx to migrate from.

**Prerequisites:**
- useSound hook migrated
- Tailwind theme with button colors

**Implementation Steps:**
- Create new base Button component with variants (primary, secondary, danger, success)
- Add size variants (sm, md, lg)
- Integrate sound effect on click (click sound)
- Add loading state with spinner
- Style with Tailwind using design tokens (button colors, rounded corners)
- Convert GenerateButton to use base Button with specific generate styling
- Add proper disabled states and focus rings for accessibility

**Verification Checklist:**
- [ ] Button variants display correctly
- [ ] Click sound plays on press
- [ ] Loading state shows spinner
- [ ] Disabled state is visually distinct
- [ ] Focus ring visible for keyboard navigation

**Testing Instructions:**
- Unit test Button renders all variants
- Test click handler fires correctly
- Test loading and disabled states
- Test sound plays on click (mocked)

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

feat(components): add Button component with variants

Create reusable Button with size and color variants
Integrate click sound effect
Add loading and disabled states
Migrate GenerateButton to use base component
```

---

### Task 6: Migrate Modal Component

**Goal:** Convert Modal to TypeScript with Tailwind and sound effects.

**Files to Modify/Create:**
- `frontend/src/components/common/Modal.tsx` - Rename and convert
- Delete: `frontend/src/components/common/Modal.jsx`
- Delete: `frontend/src/components/common/Modal.module.css`

**Prerequisites:**
- Button component migrated
- useSound hook available

**Implementation Steps:**
- Convert Modal.jsx to Modal.tsx with typed props
- Replace CSS Module with Tailwind (overlay, panel, transitions)
- Add expand sound effect when modal opens
- Use createPortal for proper DOM placement
- Implement focus trap for accessibility
- Add escape key handler to close
- Style panel with design tokens (dark background, accent border)

**Verification Checklist:**
- [ ] Modal opens and closes correctly
- [ ] Overlay covers entire screen
- [ ] Expand sound plays on open
- [ ] Escape key closes modal
- [ ] Focus trapped within modal
- [ ] Clicking overlay closes modal

**Testing Instructions:**
- Unit test Modal open/close behavior
- Test keyboard accessibility (escape, tab trapping)
- Test sound plays on open (mocked)
- Manual test: verify visual appearance

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate Modal to TypeScript

Convert Modal to TSX with Tailwind
Add expand sound effect on open
Implement focus trap and keyboard handling
```

---

### Task 7: Create Toast Component and Migrate Toast System

**Goal:** Create a new Toast component and convert the toast notification system to TypeScript with new styling.

**Files to Modify/Create:**
- `frontend/src/components/common/Toast.tsx` - **New component** (no existing Toast.jsx)
- `frontend/src/components/common/ToastContainer.tsx` - Rename and convert
- `frontend/src/context/ToastContext.tsx` - Keep for now, type it
- Delete: `frontend/src/components/common/ToastContainer.jsx`
- Delete: `frontend/src/components/common/ToastContainer.module.css`

**Note:** Toast.tsx is a new component extracted from ToastContainer. There is no existing Toast.jsx.

**Prerequisites:**
- Tailwind configured with semantic colors

**Implementation Steps:**
- Convert ToastContext to TypeScript with proper types
- Create new Toast component with variants (success, error, warning, info)
- Convert ToastContainer to manage toast stack
- Style with Tailwind using semantic colors
- Add swoosh sound when toast appears
- Implement auto-dismiss with progress indicator
- Add manual dismiss button

**Verification Checklist:**
- [ ] Toast variants display with correct colors
- [ ] Toasts stack correctly (newest on top or bottom)
- [ ] Auto-dismiss works after timeout
- [ ] Manual dismiss works
- [ ] Swoosh sound plays on appear

**Testing Instructions:**
- Unit test Toast renders correct variant
- Test ToastContainer manages multiple toasts
- Test auto-dismiss timing
- Test sound plays (mocked)

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate Toast system to TypeScript

Convert Toast and ToastContainer to TSX
Add typed variants (success, error, warning, info)
Integrate swoosh sound on appear
```

---

### Task 8: Migrate Loading Components

**Goal:** Convert loading indicators to TypeScript with playful animations.

**Files to Modify/Create:**
- `frontend/src/components/common/LoadingSpinner.tsx` - Rename and convert
- `frontend/src/components/common/LoadingSkeleton.tsx` - Rename and convert
- Delete: `frontend/src/components/common/LoadingSpinner.jsx`
- Delete: `frontend/src/components/common/LoadingSpinner.module.css`
- Delete: `frontend/src/components/common/LoadingSkeleton.jsx`
- Delete: `frontend/src/components/common/LoadingSkeleton.module.css`

**Prerequisites:**
- Tailwind animation utilities configured

**Implementation Steps:**
- Convert LoadingSpinner to TypeScript with size variants
- Use Tailwind's animate-spin or custom animation
- Style spinner with accent color
- Convert LoadingSkeleton with pulse animation
- Make skeleton accept shape prop (rectangle, circle, text)
- Use Tailwind's animate-pulse for skeleton effect
- Add playful touch to loading states (could use accent colors)

**Verification Checklist:**
- [ ] Spinner animates smoothly
- [ ] Skeleton pulses with correct colors
- [ ] Size variants work correctly
- [ ] Animations respect reduced-motion preference

**Testing Instructions:**
- Unit test components render with different sizes
- Test skeleton shape variants
- Manual test: verify animations are smooth

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate loading components to TypeScript

Convert LoadingSpinner with size variants
Convert LoadingSkeleton with shape variants
Use Tailwind animations with accent colors
```

---

### Task 9: Migrate Container and Footer

**Goal:** Convert remaining structural components to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/common/Container.tsx` - Rename and convert
- `frontend/src/components/common/Footer.tsx` - Rename and convert
- Delete: `frontend/src/components/common/Container.jsx`
- Delete: `frontend/src/components/common/Container.module.css`
- Delete: `frontend/src/components/common/Footer.jsx`
- Delete: `frontend/src/components/common/Footer.module.css`

**Prerequisites:**
- Tailwind spacing configured

**Implementation Steps:**
- Convert Container to TypeScript with max-width and padding
- Use Tailwind's container utilities or custom implementation
- Convert Footer to TypeScript with simple styling
- Style Footer to match reference aesthetic
- Ensure Container is responsive (padding changes on breakpoints)
- Keep components simple and focused

**Verification Checklist:**
- [ ] Container constrains content width correctly
- [ ] Footer displays at bottom of page
- [ ] Responsive padding works
- [ ] No TypeScript errors

**Testing Instructions:**
- Unit test Container renders children
- Test Container applies correct max-width
- Manual test: verify layout appearance

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate Container and Footer to TypeScript

Convert Container with responsive padding
Convert Footer with playful styling
Replace CSS Modules with Tailwind
```

---

### Task 10: Migrate Error Components

**Goal:** Convert error boundary and error fallback to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/features/errors/ErrorBoundary.tsx` - Rename and convert
- `frontend/src/components/features/errors/ErrorFallback.tsx` - Rename and convert
- Delete: `frontend/src/components/features/errors/ErrorBoundary.jsx`
- Delete: `frontend/src/components/features/errors/ErrorFallback.jsx`
- Delete: `frontend/src/components/features/errors/ErrorFallback.css`

**Prerequisites:**
- Button component migrated

**Implementation Steps:**
- Convert ErrorBoundary class component to TypeScript
- Type componentDidCatch error and errorInfo parameters
- Convert ErrorFallback with typed props
- Style with Tailwind using error semantic color
- Add retry button using new Button component
- Make error message user-friendly, not technical

**Verification Checklist:**
- [ ] ErrorBoundary catches component errors
- [ ] ErrorFallback displays user-friendly message
- [ ] Retry button triggers reset
- [ ] Styling matches overall design

**Testing Instructions:**
- Unit test ErrorBoundary catches thrown errors
- Test ErrorFallback renders with error prop
- Test retry callback fires correctly

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate error components to TypeScript

Convert ErrorBoundary with typed error handling
Convert ErrorFallback with Tailwind styling
Add retry functionality with Button component
```

---

### Task 11: Migrate ErrorMessage Component

**Goal:** Convert the inline error message component to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/common/ErrorMessage.tsx` - Rename and convert
- Delete: `frontend/src/components/common/ErrorMessage.jsx`
- Delete: `frontend/src/components/common/ErrorMessage.css`

**Prerequisites:**
- Tailwind configured with semantic colors

**Implementation Steps:**
- Convert ErrorMessage.jsx to TypeScript
- Add typed props for message and optional retry
- Replace CSS with Tailwind error styling
- Make dismissible if appropriate
- Ensure consistent with ErrorFallback styling

**Verification Checklist:**
- [ ] ErrorMessage renders with message prop
- [ ] Styling uses error semantic color
- [ ] Component is accessible
- [ ] No TypeScript errors

**Testing Instructions:**
- Unit test renders with different messages
- Test optional props work correctly

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate ErrorMessage to TypeScript

Convert to TSX with typed props
Replace CSS with Tailwind styling
```

---

### Task 12: Migrate Expand Component

**Goal:** Convert the expand/collapse component to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/common/Expand.tsx` - Rename and convert
- Delete: `frontend/src/components/common/Expand.jsx`
- Delete: `frontend/src/components/common/Expand.module.css`

**Prerequisites:**
- useSound hook available for expand sound

**Implementation Steps:**
- Convert Expand.jsx to TypeScript
- Add typed props for expanded state and children
- Replace CSS Module with Tailwind transitions
- Integrate expand sound effect when opening
- Add smooth height animation with Tailwind

**Verification Checklist:**
- [ ] Expand/collapse works smoothly
- [ ] Sound plays on expand
- [ ] Animation respects reduced motion
- [ ] No TypeScript errors

**Testing Instructions:**
- Unit test toggle behavior
- Test sound plays on expand (mocked)

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate Expand to TypeScript

Convert to TSX with Tailwind transitions
Add expand sound integration
```

---

### Task 13: Migrate KeyboardShortcutsHelp Component

**Goal:** Convert the keyboard shortcuts help overlay to TypeScript.

**Files to Modify/Create:**
- `frontend/src/components/common/KeyboardShortcutsHelp.tsx` - Rename and convert
- Delete: `frontend/src/components/common/KeyboardShortcutsHelp.jsx`
- Delete: `frontend/src/components/common/KeyboardShortcutsHelp.module.css`

**Prerequisites:**
- Modal component available

**Implementation Steps:**
- Convert KeyboardShortcutsHelp.jsx to TypeScript
- Use Modal component for overlay if appropriate
- Replace CSS Module with Tailwind styling
- Style keyboard keys with distinctive styling
- Ensure proper accessibility for screen readers

**Verification Checklist:**
- [ ] Shortcuts display correctly
- [ ] Modal-like behavior works
- [ ] Keyboard key styling is clear
- [ ] Accessible to screen readers

**Testing Instructions:**
- Unit test renders shortcut list
- Test open/close behavior

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate KeyboardShortcutsHelp to TypeScript

Convert to TSX with Tailwind styling
Style keyboard shortcuts clearly
```

---

### Task 14: Update App Root Component

**Goal:** Convert App.jsx to TypeScript and integrate new layout system.

**Files to Modify/Create:**
- `frontend/src/App.tsx` - Rename and convert
- `frontend/src/main.tsx` - Rename and update
- Delete: `frontend/src/App.jsx`
- Delete: `frontend/src/main.jsx`
- Delete: `frontend/src/App.css`
- Delete: `frontend/src/App.module.css`

**Prerequisites:**
- All core components migrated
- Layout components created

**Implementation Steps:**
- Rename main.jsx to main.tsx
- Rename App.jsx to App.tsx
- Replace CSS imports with Tailwind global styles
- Integrate ResponsiveLayout as main structure
- Wrap with ErrorBoundary at top level
- Maintain ToastContext provider (migrate to Zustand in Phase 3)
- Ensure all imports resolve correctly

**Verification Checklist:**
- [ ] App renders without errors
- [ ] Layout switches based on screen size
- [ ] ErrorBoundary wraps content
- [ ] Toast notifications work
- [ ] Hot reload still functions

**Testing Instructions:**
- Run `npm run dev` and verify app loads
- Test on different screen sizes
- Verify no TypeScript errors in console

**Commit Message Template:**
```
Author & Commiter : HatmanStack
Email : 82614182+HatmanStack@users.noreply.github.com

refactor(components): migrate App and main to TypeScript

Convert App.tsx with new layout system
Convert main.tsx entry point
Remove legacy CSS files
```

---

## Phase Verification

After completing all tasks in this phase:

1. **TypeScript Check:**
   ```bash
   npx tsc --noEmit
   # Should pass for all migrated components
   ```

2. **Visual Check:**
   - Breathing header animation visible and smooth
   - Layout switches between desktop/mobile correctly
   - All buttons have correct styling
   - Modal opens/closes with animation

3. **Sound Check:**
   - Click buttons and hear click sound
   - Open modal and hear expand sound
   - Trigger toast and hear swoosh sound
   - Mute toggle silences all sounds

4. **Accessibility Check:**
   - Tab through interface, focus rings visible
   - Escape closes modal
   - Screen reader announces toast notifications

5. **Test Check:**
   ```bash
   npm test
   # Core component tests should pass
   ```

### Integration Points

- ResponsiveLayout ready to receive Generation and Gallery components (Phase 3)
- Button, Modal, Toast ready for use in feature components
- Sound system integrated and functional
- Error handling covers all routes

### Known Limitations

- Feature components (Generation, Gallery) still JSX (Phase 3)
- Context still used for Toast (migrate in Phase 3)
- Some CSS Module files may still exist for unmigrated components

### Technical Debt

- ToastContext should move to Zustand
- Consider extracting animation utilities to shared file
- Button variants could be more comprehensive
