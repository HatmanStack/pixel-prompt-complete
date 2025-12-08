# Phase 2: Frontend Redesign

## Phase Goal

Transform the frontend from a 9-image grid to a 4-column layout with per-model iteration support. Each column displays one model's original image plus up to 7 iterations, with per-column prompt input, multi-select capability, and outpainting controls. The gallery is reorganized to group sessions by original prompt with nested iterations.

**Success Criteria:**
- 4-column layout displays one model per column
- Each column shows original + iterations vertically
- Per-column text input for iteration prompts
- Checkbox overlay enables multi-select for batch operations
- Outpaint preset buttons (16:9, 9:16, 1:1, 4:3, Expand All)
- Warning displayed at iteration 5, input disabled at 7
- Gallery groups sessions by prompt with expandable iterations
- All frontend tests pass with mocked API

**Estimated Tokens:** ~40,000

## Prerequisites

- Phase 1 complete (backend API ready)
- Backend deployed with at least one model enabled
- Frontend development environment running

---

## Task 1: Update TypeScript Types

**Goal:** Define new TypeScript interfaces for session-based data structures.

**Files to Modify/Create:**
- `frontend/src/types/index.ts` - Update/add type definitions
- `frontend/src/types/api.ts` - Update API response types

**Prerequisites:**
- None (first task)

**Implementation Steps:**

1. **Define model enumeration:**
   ```typescript
   export type ModelName = 'flux' | 'recraft' | 'gemini' | 'openai';

   export const MODEL_DISPLAY_NAMES: Record<ModelName, string> = {
     flux: 'Flux',
     recraft: 'Recraft',
     gemini: 'Gemini',
     openai: 'OpenAI',
   };
   ```

2. **Define iteration types:**
   ```typescript
   export type IterationStatus = 'pending' | 'loading' | 'completed' | 'error';

   export interface Iteration {
     index: number;
     status: IterationStatus;
     prompt: string;
     imageUrl?: string;
     error?: string;
     completedAt?: string;
   }
   ```

3. **Define model column types:**
   ```typescript
   export interface ModelColumn {
     name: ModelName;
     enabled: boolean;
     status: IterationStatus;
     iterations: Iteration[];
   }
   ```

4. **Define session types:**
   ```typescript
   export interface Session {
     sessionId: string;
     status: 'pending' | 'in_progress' | 'completed' | 'partial' | 'failed';
     prompt: string;
     createdAt: string;
     updatedAt: string;
     models: Record<ModelName, ModelColumn>;
   }
   ```

5. **Define API response types:**
   ```typescript
   export interface GenerateResponse {
     sessionId: string;
     status: string;
   }

   export interface IterateResponse {
     sessionId: string;
     model: ModelName;
     iteration: number;
     status: string;
   }

   export interface OutpaintResponse {
     sessionId: string;
     model: ModelName;
     iteration: number;
     status: string;
   }

   export type OutpaintPreset = '16:9' | '9:16' | '1:1' | '4:3' | 'expand_all';
   ```

6. **Define selection types:**
   ```typescript
   export interface SelectionState {
     selectedModels: Set<ModelName>;
     isMultiSelectMode: boolean;
   }
   ```

**Verification Checklist:**
- [ ] All types compile without errors
- [ ] Types match backend API response format
- [ ] Discriminated unions for status handling
- [ ] No `any` types used

**Testing Instructions:**
- TypeScript compilation: `npm run typecheck`
- Types used correctly in subsequent tasks

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): add TypeScript types for session-based architecture

Define ModelName enum and display names
Add Iteration and ModelColumn interfaces
Define Session type with model mapping
Add API response types for new endpoints
Define OutpaintPreset and SelectionState types
```

---

## Task 2: Update Zustand Store

**Goal:** Restructure the app store for session-based state with per-model iteration tracking.

**Files to Modify/Create:**
- `frontend/src/stores/useAppStore.ts` - Complete rewrite

**Prerequisites:**
- Task 1 complete (types defined)

**Implementation Steps:**

1. **Define store state interface:**
   ```typescript
   interface AppState {
     // Session state
     currentSession: Session | null;
     isGenerating: boolean;
     prompt: string;

     // Selection state
     selectedModels: Set<ModelName>;
     isMultiSelectMode: boolean;

     // Gallery state
     sessions: SessionPreview[];
     selectedGallerySession: Session | null;

     // UI state
     iterationWarnings: Record<ModelName, boolean>;  // Show warning at 5
   }
   ```

2. **Define store actions:**
   ```typescript
   interface AppActions {
     // Prompt
     setPrompt: (prompt: string) => void;

     // Session
     setCurrentSession: (session: Session | null) => void;
     updateModelIteration: (model: ModelName, iteration: Iteration) => void;
     setIsGenerating: (isGenerating: boolean) => void;
     resetSession: () => void;

     // Selection
     toggleModelSelection: (model: ModelName) => void;
     selectAllModels: () => void;
     clearSelection: () => void;
     setMultiSelectMode: (enabled: boolean) => void;

     // Gallery
     setSessions: (sessions: SessionPreview[]) => void;
     setSelectedGallerySession: (session: Session | null) => void;

     // Warnings
     checkIterationWarning: (model: ModelName) => void;
   }
   ```

3. **Implement iteration warning logic:**
   ```typescript
   checkIterationWarning: (model) => set((state) => {
     const column = state.currentSession?.models[model];
     if (column && column.iterations.length >= 5) {
       return {
         iterationWarnings: {
           ...state.iterationWarnings,
           [model]: true
         }
       };
     }
     return state;
   }),
   ```

4. **Remove old job-based state** (currentJob, generatedImages array).

**Verification Checklist:**
- [ ] Store initializes with empty session
- [ ] `updateModelIteration()` updates correct model
- [ ] Selection state tracks multiple models
- [ ] Warning triggers at iteration 5
- [ ] No references to old job-based state

**Testing Instructions:**
- Unit tests for store actions
- Test selection state management
- Test warning trigger logic

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

refactor(frontend): restructure store for session-based state

Replace job-based state with session structure
Add per-model selection state with Set
Implement iteration warning at count 5
Add gallery session state
Remove deprecated job/image array state
```

---

## Task 3: Update API Client

**Goal:** Add API methods for `/iterate` and `/outpaint` endpoints.

**Files to Modify/Create:**
- `frontend/src/api/client.ts` - Add new methods
- `frontend/src/api/config.ts` - Add new routes

**Prerequisites:**
- Task 1 complete (types defined)

**Implementation Steps:**

1. **Add API routes:**
   ```typescript
   // config.ts
   export const API_ROUTES = {
     GENERATE: '/generate',
     ITERATE: '/iterate',
     OUTPAINT: '/outpaint',
     STATUS: '/status',
     GALLERY_LIST: '/gallery/list',
     GALLERY_DETAIL: '/gallery',
   };
   ```

2. **Add `iterateImage()` method:**
   ```typescript
   export async function iterateImage(
     sessionId: string,
     model: ModelName,
     prompt: string
   ): Promise<IterateResponse> {
     return apiFetch<IterateResponse>(API_ROUTES.ITERATE, {
       method: 'POST',
       body: JSON.stringify({ sessionId, model, prompt }),
     });
   }
   ```

3. **Add `outpaintImage()` method:**
   ```typescript
   export async function outpaintImage(
     sessionId: string,
     model: ModelName,
     iterationIndex: number,
     preset: OutpaintPreset,
     prompt: string
   ): Promise<OutpaintResponse> {
     return apiFetch<OutpaintResponse>(API_ROUTES.OUTPAINT, {
       method: 'POST',
       body: JSON.stringify({
         sessionId,
         model,
         iterationIndex,
         preset,
         prompt
       }),
     });
   }
   ```

4. **Update `getSessionStatus()` method:**
   ```typescript
   export async function getSessionStatus(sessionId: string): Promise<Session> {
     return apiFetch<Session>(`${API_ROUTES.STATUS}/${sessionId}`);
   }
   ```

5. **Add batch iteration method for multi-select:**
   ```typescript
   export async function iterateMultiple(
     sessionId: string,
     models: ModelName[],
     prompt: string
   ): Promise<IterateResponse[]> {
     return Promise.all(
       models.map(model => iterateImage(sessionId, model, prompt))
     );
   }
   ```

**Verification Checklist:**
- [ ] All methods return typed responses
- [ ] Request bodies match API contract
- [ ] Error handling consistent with existing patterns
- [ ] Batch method handles partial failures

**Testing Instructions:**
- Unit tests with mocked fetch
- Test error response handling

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): add API methods for iterate and outpaint

Implement iterateImage() for single model iteration
Implement outpaintImage() with preset parameter
Add iterateMultiple() for batch operations
Update getSessionStatus() for new response format
```

---

## Task 4: Create Session Polling Hook

**Goal:** Create a hook to poll session status and update store progressively.

**Files to Modify/Create:**
- `frontend/src/hooks/useSessionPolling.ts` - New hook

**Prerequisites:**
- Task 2 complete (store)
- Task 3 complete (API client)

**Implementation Steps:**

1. **Create polling hook:**
   ```typescript
   export function useSessionPolling(sessionId: string | null, intervalMs = 2000) {
     const { setCurrentSession, setIsGenerating } = useAppStore();
     const [error, setError] = useState<string | null>(null);

     useEffect(() => {
       if (!sessionId) return;

       let mounted = true;
       let consecutiveErrors = 0;
       const maxErrors = 5;

       const poll = async () => {
         try {
           const session = await getSessionStatus(sessionId);
           if (!mounted) return;

           setCurrentSession(session);
           consecutiveErrors = 0;

           // Check if complete
           if (['completed', 'partial', 'failed'].includes(session.status)) {
             setIsGenerating(false);
             return; // Stop polling
           }

           // Continue polling
           setTimeout(poll, intervalMs);
         } catch (err) {
           consecutiveErrors++;
           if (consecutiveErrors >= maxErrors) {
             setError('Failed to get status after multiple attempts');
             setIsGenerating(false);
             return;
           }
           // Exponential backoff
           setTimeout(poll, intervalMs * Math.pow(2, consecutiveErrors));
         }
       };

       poll();

       return () => {
         mounted = false;
       };
     }, [sessionId, intervalMs]);

     return { error };
   }
   ```

2. **Handle iteration-specific updates:**
   - Update individual model columns as they complete
   - Progressive display of results

3. **Add timeout protection:**
   - Stop polling after 5 minutes
   - Show appropriate error message

**Verification Checklist:**
- [ ] Polling starts when sessionId provided
- [ ] Store updated with each poll response
- [ ] Polling stops on completion/failure
- [ ] Exponential backoff on errors
- [ ] Cleanup on unmount

**Testing Instructions:**
- Unit tests with mocked API
- Test error handling and backoff

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): add useSessionPolling hook

Poll session status every 2 seconds
Update store with progressive results
Stop polling on completion/failure
Implement exponential backoff on errors
Add 5-minute timeout protection
```

---

## Task 5: Create Iteration Hook

**Goal:** Create a hook to manage iteration logic including limit checking and API calls.

**Files to Modify/Create:**
- `frontend/src/hooks/useIteration.ts` - New hook

**Prerequisites:**
- Task 2 complete (store)
- Task 3 complete (API client)

**Implementation Steps:**

1. **Create iteration hook:**
   ```typescript
   export function useIteration(model: ModelName) {
     const {
       currentSession,
       checkIterationWarning,
       iterationWarnings,
     } = useAppStore();

     const column = currentSession?.models[model];
     const iterationCount = column?.iterations.length ?? 0;
     const isAtLimit = iterationCount >= 7;
     const showWarning = iterationWarnings[model];

     const iterate = async (prompt: string): Promise<void> => {
       if (!currentSession || isAtLimit) return;

       try {
         await iterateImage(currentSession.sessionId, model, prompt);
         checkIterationWarning(model);
       } catch (err) {
         // Handle error
         throw err;
       }
     };

     return {
       iterate,
       iterationCount,
       isAtLimit,
       showWarning,
       remainingIterations: 7 - iterationCount,
     };
   }
   ```

2. **Add multi-model iteration:**
   ```typescript
   export function useMultiIterate() {
     const { currentSession, selectedModels, clearSelection } = useAppStore();

     const iterateSelected = async (prompt: string): Promise<void> => {
       if (!currentSession || selectedModels.size === 0) return;

       const models = Array.from(selectedModels);
       await iterateMultiple(currentSession.sessionId, models, prompt);
       clearSelection();
     };

     return { iterateSelected, selectedCount: selectedModels.size };
   }
   ```

**Verification Checklist:**
- [ ] `iterate()` calls API correctly
- [ ] `isAtLimit` true at 7 iterations
- [ ] `showWarning` true at 5+ iterations
- [ ] Multi-iterate handles all selected models
- [ ] Selection cleared after batch operation

**Testing Instructions:**
- Unit tests for limit logic
- Test with mocked API calls

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): add useIteration hook for iteration management

Track iteration count and limit per model
Provide isAtLimit and showWarning flags
Implement iterate() for single model
Add useMultiIterate() for batch operations
Clear selection after batch iteration
```

---

## Task 6: Create ModelColumn Component

**Goal:** Create a component that displays a single model's images vertically with all iterations.

**Files to Modify/Create:**
- `frontend/src/components/generation/ModelColumn.tsx` - New component

**Prerequisites:**
- Task 1 complete (types)
- Task 5 complete (iteration hook)

**Implementation Steps:**

1. **Define component props:**
   ```typescript
   interface ModelColumnProps {
     model: ModelName;
     column: ModelColumn;
     isSelected: boolean;
     onToggleSelect: () => void;
   }
   ```

2. **Implement component structure:**
   ```tsx
   export const ModelColumn: FC<ModelColumnProps> = ({
     model,
     column,
     isSelected,
     onToggleSelect,
   }) => {
     return (
       <div className="flex flex-col gap-4 min-w-[250px] max-w-[300px]">
         {/* Header with model name and checkbox */}
         <div className="flex items-center justify-between">
           <h3>{MODEL_DISPLAY_NAMES[model]}</h3>
           <Checkbox
             checked={isSelected}
             onChange={onToggleSelect}
             aria-label={`Select ${model} for batch editing`}
           />
         </div>

         {/* Iterations list */}
         <div className="flex flex-col gap-2 overflow-y-auto max-h-[60vh]">
           {column.iterations.map((iteration) => (
             <IterationCard
               key={iteration.index}
               model={model}
               iteration={iteration}
             />
           ))}
         </div>

         {/* Per-column input */}
         {!isAtLimit && (
           <IterationInput model={model} />
         )}

         {/* Outpaint controls */}
         <OutpaintControls model={model} />
       </div>
     );
   };
   ```

3. **Style for vertical scrolling:**
   - Fixed column width (250-300px)
   - Max height with overflow scroll
   - Sticky header

4. **Handle disabled state:**
   - Show "Not enabled" if `column.enabled === false`
   - Gray out entire column

**Verification Checklist:**
- [ ] Displays all iterations vertically
- [ ] Checkbox toggles selection
- [ ] Scrolls when iterations exceed viewport
- [ ] Input hidden when at limit
- [ ] Disabled state handled

**Testing Instructions:**
- Unit tests for render states
- Test with various iteration counts

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): create ModelColumn component

Display model name with selection checkbox
Render iterations vertically with scroll
Include per-column iteration input
Add outpaint controls below iterations
Handle disabled model state
```

---

## Task 7: Create IterationCard Component

**Goal:** Create a component that displays a single iteration with image, status, and metadata.

**Files to Modify/Create:**
- `frontend/src/components/generation/IterationCard.tsx` - New component

**Prerequisites:**
- Task 1 complete (types)

**Implementation Steps:**

1. **Define component props:**
   ```typescript
   interface IterationCardProps {
     model: ModelName;
     iteration: Iteration;
     onExpand?: () => void;
   }
   ```

2. **Implement status-based rendering:**
   ```tsx
   export const IterationCard: FC<IterationCardProps> = ({
     model,
     iteration,
     onExpand,
   }) => {
     return (
       <div className="relative rounded-lg overflow-hidden border">
         {/* Status indicator badge */}
         <div className="absolute top-2 left-2 z-10">
           <StatusBadge status={iteration.status} />
         </div>

         {/* Image or placeholder */}
         {iteration.status === 'completed' && iteration.imageUrl ? (
           <img
             src={iteration.imageUrl}
             alt={`${model} iteration ${iteration.index}`}
             className="w-full aspect-square object-cover cursor-pointer"
             onClick={onExpand}
           />
         ) : iteration.status === 'loading' ? (
           <LoadingSkeleton />
         ) : iteration.status === 'error' ? (
           <ErrorState error={iteration.error} />
         ) : (
           <PendingPlaceholder />
         )}

         {/* Iteration number and prompt preview */}
         <div className="p-2 bg-surface">
           <span className="text-xs text-text-secondary">
             #{iteration.index}: {truncate(iteration.prompt, 50)}
           </span>
         </div>
       </div>
     );
   };
   ```

3. **Add expand functionality:**
   - Click opens modal with full-size image
   - Modal shows full prompt and metadata

4. **Style for compact display:**
   - Square aspect ratio
   - Small text for metadata
   - Hover effects

**Verification Checklist:**
- [ ] Renders correctly for each status
- [ ] Image clickable for expansion
- [ ] Prompt truncated appropriately
- [ ] Error message displayed
- [ ] Loading state animated

**Testing Instructions:**
- Unit tests for each status state
- Snapshot tests for visual consistency

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): create IterationCard component

Render iteration based on status
Display image with click-to-expand
Show truncated prompt and iteration number
Handle loading, error, and pending states
Add status badge indicator
```

---

## Task 8: Create IterationInput Component

**Goal:** Create a per-column text input for iteration prompts with warning display.

**Files to Modify/Create:**
- `frontend/src/components/generation/IterationInput.tsx` - New component

**Prerequisites:**
- Task 5 complete (iteration hook)

**Implementation Steps:**

1. **Define component props:**
   ```typescript
   interface IterationInputProps {
     model: ModelName;
   }
   ```

2. **Implement input with warning:**
   ```tsx
   export const IterationInput: FC<IterationInputProps> = ({ model }) => {
     const [prompt, setPrompt] = useState('');
     const { iterate, isAtLimit, showWarning, remainingIterations } = useIteration(model);
     const [isSubmitting, setIsSubmitting] = useState(false);

     const handleSubmit = async () => {
       if (!prompt.trim() || isAtLimit || isSubmitting) return;

       setIsSubmitting(true);
       try {
         await iterate(prompt);
         setPrompt('');
       } finally {
         setIsSubmitting(false);
       }
     };

     if (isAtLimit) {
       return (
         <div className="text-sm text-text-secondary text-center p-2">
           Maximum iterations reached (7)
         </div>
       );
     }

     return (
       <div className="flex flex-col gap-2">
         {showWarning && (
           <div className="text-sm text-warning bg-warning/10 p-2 rounded">
             {remainingIterations} iterations remaining
           </div>
         )}

         <div className="flex gap-2">
           <input
             type="text"
             value={prompt}
             onChange={(e) => setPrompt(e.target.value)}
             placeholder="Refine this image..."
             className="flex-1 px-3 py-2 rounded border"
             onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
             disabled={isSubmitting}
           />
           <button
             onClick={handleSubmit}
             disabled={!prompt.trim() || isSubmitting}
             className="px-4 py-2 bg-accent text-white rounded"
           >
             {isSubmitting ? '...' : 'Go'}
           </button>
         </div>
       </div>
     );
   };
   ```

3. **Add keyboard support:**
   - Enter to submit
   - Escape to clear

**Verification Checklist:**
- [ ] Input clears after submission
- [ ] Warning displays at 5+ iterations
- [ ] Input disabled during submission
- [ ] Hidden when at limit (7)
- [ ] Keyboard shortcuts work

**Testing Instructions:**
- Unit tests for warning display
- Test submission flow
- Test limit behavior

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): create IterationInput component

Add per-column text input for iteration prompts
Display warning when 3 iterations remaining
Hide input when limit reached (7)
Add submit button with loading state
Support Enter key submission
```

---

## Task 9: Create OutpaintControls Component

**Goal:** Create outpainting preset buttons for each model column.

**Files to Modify/Create:**
- `frontend/src/components/generation/OutpaintControls.tsx` - New component

**Prerequisites:**
- Task 3 complete (API client)
- Task 5 complete (iteration hook)

**Implementation Steps:**

1. **Define component props:**
   ```typescript
   interface OutpaintControlsProps {
     model: ModelName;
   }
   ```

2. **Define presets:**
   ```typescript
   const PRESETS: { value: OutpaintPreset; label: string }[] = [
     { value: '16:9', label: '16:9' },
     { value: '9:16', label: '9:16' },
     { value: '1:1', label: '1:1' },
     { value: '4:3', label: '4:3' },
     { value: 'expand_all', label: 'Expand' },
   ];
   ```

3. **Implement controls:**
   ```tsx
   export const OutpaintControls: FC<OutpaintControlsProps> = ({ model }) => {
     const { currentSession } = useAppStore();
     const { isAtLimit } = useIteration(model);
     const [selectedPreset, setSelectedPreset] = useState<OutpaintPreset | null>(null);
     const [prompt, setPrompt] = useState('');
     const [isSubmitting, setIsSubmitting] = useState(false);

     const column = currentSession?.models[model];
     const latestIteration = column?.iterations.slice(-1)[0];

     const handleOutpaint = async () => {
       if (!currentSession || !selectedPreset || !latestIteration || isAtLimit) return;

       setIsSubmitting(true);
       try {
         await outpaintImage(
           currentSession.sessionId,
           model,
           latestIteration.index,
           selectedPreset,
           prompt
         );
         setSelectedPreset(null);
         setPrompt('');
       } finally {
         setIsSubmitting(false);
       }
     };

     if (isAtLimit || !latestIteration) return null;

     return (
       <div className="flex flex-col gap-2 p-2 bg-surface rounded">
         <span className="text-xs text-text-secondary">Expand image:</span>

         <div className="flex flex-wrap gap-1">
           {PRESETS.map(({ value, label }) => (
             <button
               key={value}
               onClick={() => setSelectedPreset(value)}
               className={cn(
                 'px-2 py-1 text-xs rounded',
                 selectedPreset === value
                   ? 'bg-accent text-white'
                   : 'bg-secondary'
               )}
             >
               {label}
             </button>
           ))}
         </div>

         {selectedPreset && (
           <div className="flex gap-2">
             <input
               type="text"
               value={prompt}
               onChange={(e) => setPrompt(e.target.value)}
               placeholder="Describe expanded area..."
               className="flex-1 px-2 py-1 text-sm rounded border"
             />
             <button
               onClick={handleOutpaint}
               disabled={isSubmitting}
               className="px-3 py-1 text-sm bg-accent text-white rounded"
             >
               {isSubmitting ? '...' : 'Expand'}
             </button>
           </div>
         )}
       </div>
     );
   };
   ```

**Verification Checklist:**
- [ ] All 5 presets displayed
- [ ] Selected preset highlighted
- [ ] Prompt input appears on selection
- [ ] Hidden when at limit
- [ ] Calls API with correct parameters

**Testing Instructions:**
- Unit tests for preset selection
- Test API call parameters

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): create OutpaintControls component

Display 5 aspect preset buttons
Show prompt input when preset selected
Call outpaintImage API on submit
Hide controls when iteration limit reached
Style for compact display in column
```

---

## Task 10: Update GenerationPanel Layout

**Goal:** Restructure GenerationPanel to display 4 horizontal columns instead of a grid.

**Files to Modify/Create:**
- `frontend/src/components/generation/GenerationPanel.tsx` - Major rewrite

**Prerequisites:**
- Task 4 complete (session polling hook)
- Task 6 complete (ModelColumn component)

**Implementation Steps:**

1. **Replace grid with horizontal columns:**
   ```tsx
   export const GenerationPanel: FC = () => {
     const {
       prompt,
       setPrompt,
       currentSession,
       isGenerating,
       selectedModels,
       toggleModelSelection,
     } = useAppStore();

     const { error: pollingError } = useSessionPolling(
       currentSession?.sessionId ?? null
     );

     return (
       <article className="w-full flex flex-col gap-8">
         {/* Prompt Input Section */}
         <section className="flex flex-col gap-4">
           <PromptInput
             value={prompt}
             onChange={setPrompt}
             disabled={isGenerating}
           />

           <div className="flex gap-4">
             <GenerateButton
               onClick={handleGenerate}
               disabled={!prompt.trim() || isGenerating}
               isGenerating={isGenerating}
             />

             {selectedModels.size > 0 && (
               <MultiIterateInput selectedCount={selectedModels.size} />
             )}
           </div>

           {/* Progress indicator */}
           {isGenerating && <ProgressBar session={currentSession} />}

           {/* Error display */}
           {pollingError && <ErrorBanner error={pollingError} />}
         </section>

         {/* 4-Column Layout */}
         <section className="flex gap-4 overflow-x-auto pb-4">
           {MODELS.map((model) => {
             const column = currentSession?.models[model];
             return (
               <ModelColumn
                 key={model}
                 model={model}
                 column={column ?? createEmptyColumn(model)}
                 isSelected={selectedModels.has(model)}
                 onToggleSelect={() => toggleModelSelection(model)}
               />
             );
           })}
         </section>

         {/* Gallery Section */}
         <section>
           <GalleryBrowser />
         </section>
       </article>
     );
   };
   ```

2. **Handle horizontal scrolling:**
   - On mobile: Horizontal scroll with snap points
   - On desktop: All 4 columns visible

3. **Add multi-iterate input:**
   - Appears when models selected
   - Single input affects all selected

4. **Style for responsive layout:**
   ```css
   /* Mobile: horizontal scroll */
   @media (max-width: 768px) {
     .columns-container {
       scroll-snap-type: x mandatory;
     }
     .model-column {
       scroll-snap-align: center;
       min-width: 80vw;
     }
   }
   ```

**Verification Checklist:**
- [ ] 4 columns display horizontally
- [ ] Columns scroll on mobile
- [ ] Multi-select input appears when models selected
- [ ] Progress bar reflects overall status
- [ ] Error messages display appropriately

**Testing Instructions:**
- Visual testing at various breakpoints
- Test horizontal scroll behavior

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

refactor(frontend): restructure GenerationPanel for 4-column layout

Replace 9-image grid with 4 horizontal columns
Add horizontal scroll for mobile
Show multi-iterate input when models selected
Update progress bar for session status
Integrate session polling hook
```

---

## Task 11: Create MultiIterateInput Component

**Goal:** Create a shared input for batch iteration when multiple models are selected.

**Files to Modify/Create:**
- `frontend/src/components/generation/MultiIterateInput.tsx` - New component

**Prerequisites:**
- Task 5 complete (useMultiIterate hook)

**Implementation Steps:**

1. **Define component props:**
   ```typescript
   interface MultiIterateInputProps {
     selectedCount: number;
   }
   ```

2. **Implement shared input:**
   ```tsx
   export const MultiIterateInput: FC<MultiIterateInputProps> = ({
     selectedCount,
   }) => {
     const [prompt, setPrompt] = useState('');
     const { iterateSelected } = useMultiIterate();
     const [isSubmitting, setIsSubmitting] = useState(false);

     const handleSubmit = async () => {
       if (!prompt.trim() || isSubmitting) return;

       setIsSubmitting(true);
       try {
         await iterateSelected(prompt);
         setPrompt('');
       } finally {
         setIsSubmitting(false);
       }
     };

     return (
       <div className="flex items-center gap-2 p-3 bg-accent/10 rounded-lg">
         <span className="text-sm font-medium">
           Edit {selectedCount} image{selectedCount > 1 ? 's' : ''}:
         </span>

         <input
           type="text"
           value={prompt}
           onChange={(e) => setPrompt(e.target.value)}
           placeholder="Apply to all selected..."
           className="flex-1 px-3 py-2 rounded border"
           onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
         />

         <button
           onClick={handleSubmit}
           disabled={!prompt.trim() || isSubmitting}
           className="px-4 py-2 bg-accent text-white rounded"
         >
           Apply
         </button>
       </div>
     );
   };
   ```

**Verification Checklist:**
- [ ] Shows selected count
- [ ] Clears selection after submit
- [ ] Handles partial failures gracefully

**Testing Instructions:**
- Test with various selection counts
- Test batch API call

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): create MultiIterateInput for batch iteration

Display selected model count
Provide shared input for batch prompts
Clear selection after successful submission
Handle Enter key submission
```

---

## Task 12: Reorganize Gallery Components

**Goal:** Update gallery to group sessions by prompt with expandable iteration view.

**Files to Modify/Create:**
- `frontend/src/components/gallery/GalleryBrowser.tsx` - Update for session grouping
- `frontend/src/components/gallery/SessionCard.tsx` - New component
- `frontend/src/components/gallery/SessionDetail.tsx` - New component

**Prerequisites:**
- Task 1 complete (types)
- Task 2 complete (store)

**Implementation Steps:**

1. **Update GalleryBrowser:**
   ```tsx
   export const GalleryBrowser: FC = () => {
     const { sessions, setSessions } = useAppStore();
     const [expandedSession, setExpandedSession] = useState<string | null>(null);

     useEffect(() => {
       listGalleries().then((response) => {
         setSessions(response.sessions);
       });
     }, []);

     return (
       <div className="flex flex-col gap-4">
         <h2 className="text-lg font-semibold">Previous Sessions</h2>

         <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
           {sessions.map((session) => (
             <SessionCard
               key={session.sessionId}
               session={session}
               isExpanded={expandedSession === session.sessionId}
               onToggle={() => setExpandedSession(
                 expandedSession === session.sessionId ? null : session.sessionId
               )}
             />
           ))}
         </div>

         {/* Expanded session modal */}
         {expandedSession && (
           <SessionDetail
             sessionId={expandedSession}
             onClose={() => setExpandedSession(null)}
           />
         )}
       </div>
     );
   };
   ```

2. **Create SessionCard component:**
   ```tsx
   interface SessionCardProps {
     session: SessionPreview;
     isExpanded: boolean;
     onToggle: () => void;
   }

   export const SessionCard: FC<SessionCardProps> = ({
     session,
     onToggle,
   }) => {
     return (
       <div
         className="p-4 border rounded-lg cursor-pointer hover:border-accent"
         onClick={onToggle}
       >
         <img
           src={session.thumbnail}
           alt={session.prompt}
           className="w-full aspect-video object-cover rounded"
         />
         <p className="mt-2 text-sm font-medium truncate">
           {session.prompt}
         </p>
         <p className="text-xs text-text-secondary">
           {session.totalIterations} iterations · {formatDate(session.createdAt)}
         </p>
       </div>
     );
   };
   ```

3. **Create SessionDetail modal:**
   - Fetch full session data on open
   - Display all 4 model columns with iterations
   - Allow clicking to expand individual images

**Verification Checklist:**
- [ ] Sessions sorted by date (newest first)
- [ ] Thumbnail displays correctly
- [ ] Click expands to full session view
- [ ] All iterations visible in expanded view

**Testing Instructions:**
- Test with various session counts
- Test expansion behavior

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

refactor(frontend): reorganize gallery for session-based display

Group images by original prompt
Show iteration count and thumbnail
Add expandable session detail view
Display all model columns in expanded view
Sort sessions by creation date
```

---

## Task 13: Add Image Modal Component

**Goal:** Create a modal for viewing full-size images with metadata.

**Files to Modify/Create:**
- `frontend/src/components/common/ImageModal.tsx` - New component

**Prerequisites:**
- None (uses existing Modal component)

**Implementation Steps:**

1. **Define component props:**
   ```typescript
   interface ImageModalProps {
     isOpen: boolean;
     onClose: () => void;
     imageUrl: string;
     model: ModelName;
     iteration: Iteration;
     onDownload?: () => void;
   }
   ```

2. **Implement modal:**
   ```tsx
   export const ImageModal: FC<ImageModalProps> = ({
     isOpen,
     onClose,
     imageUrl,
     model,
     iteration,
     onDownload,
   }) => {
     return (
       <Modal isOpen={isOpen} onClose={onClose}>
         <div className="flex flex-col gap-4 max-w-4xl">
           <img
             src={imageUrl}
             alt={`${model} iteration ${iteration.index}`}
             className="w-full max-h-[70vh] object-contain"
           />

           <div className="flex flex-col gap-2">
             <h3 className="font-semibold">
               {MODEL_DISPLAY_NAMES[model]} - Iteration {iteration.index}
             </h3>
             <p className="text-sm">{iteration.prompt}</p>
             <p className="text-xs text-text-secondary">
               Generated: {formatDateTime(iteration.completedAt)}
             </p>
           </div>

           <div className="flex gap-2">
             <button onClick={onDownload} className="btn-secondary">
               Download
             </button>
             <button onClick={onClose} className="btn-primary">
               Close
             </button>
           </div>
         </div>
       </Modal>
     );
   };
   ```

3. **Add keyboard navigation:**
   - Escape to close
   - Arrow keys for next/prev (if applicable)

**Verification Checklist:**
- [ ] Image displays at appropriate size
- [ ] Metadata visible below image
- [ ] Download button works
- [ ] Keyboard shortcuts functional

**Testing Instructions:**
- Test at various image sizes
- Test keyboard navigation

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(frontend): add ImageModal for full-size image viewing

Display full-size image with max height constraint
Show model name, iteration number, and prompt
Add download button
Support Escape key to close
```

---

## Task 14: Frontend Unit Tests

**Goal:** Write comprehensive tests for all new frontend components and hooks.

**Files to Modify/Create:**
- `frontend/tests/__tests__/components/ModelColumn.test.tsx`
- `frontend/tests/__tests__/components/IterationCard.test.tsx`
- `frontend/tests/__tests__/components/IterationInput.test.tsx`
- `frontend/tests/__tests__/components/OutpaintControls.test.tsx`
- `frontend/tests/__tests__/hooks/useSessionPolling.test.ts`
- `frontend/tests/__tests__/hooks/useIteration.test.ts`
- `frontend/tests/__tests__/integration/IterationFlow.test.tsx`

**Prerequisites:**
- All component tasks complete

**Implementation Steps:**

1. **Add test utilities:**
   ```typescript
   // test-utils.tsx
   export function renderWithStore(
     component: ReactElement,
     initialState?: Partial<AppState>
   ) {
     // Set up Zustand store with initial state
     // Return render result with store access
   }

   export function mockSession(overrides?: Partial<Session>): Session {
     // Return mock session with sensible defaults
   }
   ```

2. **Write component tests:**
   - ModelColumn: render states, selection, scroll behavior
   - IterationCard: status variants, click handlers
   - IterationInput: warning display, limit behavior
   - OutpaintControls: preset selection, API calls

3. **Write hook tests:**
   - useSessionPolling: polling lifecycle, error handling
   - useIteration: limit checks, API calls

4. **Write integration tests:**
   - Full iteration flow from prompt to result
   - Multi-select batch iteration
   - Outpaint with preset

**Verification Checklist:**
- [ ] All tests pass: `npm test`
- [ ] Coverage >80% for new code
- [ ] No flaky tests
- [ ] Mocks used appropriately

**Testing Instructions:**
```bash
cd frontend
npm test
npm run test:coverage
```

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

test(frontend): add comprehensive tests for v2 components

Test ModelColumn render states and selection
Test IterationCard status variants
Test IterationInput warning and limit behavior
Test OutpaintControls preset selection
Test useSessionPolling lifecycle
Test useIteration limit enforcement
Add integration tests for iteration flow
Achieve 80%+ coverage on new code
```

---

## Phase Verification

### Test Suite Execution

```bash
# Run all frontend tests
cd frontend
npm test

# Run with coverage
npm run test:coverage

# Run specific test file
npm test -- ModelColumn.test.tsx
```

### Visual Verification

1. **4-Column Layout**: Start app, verify 4 horizontal columns visible
2. **Iteration Flow**: Generate images, iterate on one, verify column updates
3. **Multi-Select**: Check multiple columns, use shared input
4. **Outpaint**: Select preset, enter prompt, verify expansion
5. **Gallery**: Browse past sessions, expand to see iterations
6. **Warning**: Iterate to 5, verify warning appears
7. **Limit**: Iterate to 7, verify input disabled

### Responsive Testing

- Desktop (1920px): All 4 columns visible
- Tablet (768px): 2-3 columns, horizontal scroll
- Mobile (375px): 1 column, horizontal scroll with snap

### Accessibility Verification

- Tab navigation through columns
- Screen reader announces iteration counts
- Color contrast for warnings
- Focus states visible

### Known Limitations

1. **No drag-and-drop**: Cannot reorder columns
2. **No image zoom**: Modal shows full-size but no pan/zoom
3. **No undo**: Cannot undo iterations
4. **No comparison**: Cannot side-by-side compare iterations

---

## Completion

With Phase 2 complete, the full feature set is implemented:

1. **Phase 0**: Foundation established (ADRs, testing strategy, deploy specs)
2. **Phase 1**: Backend transformed (4 models, iterate/outpaint endpoints, sessions)
3. **Phase 2**: Frontend redesigned (columns, iteration UI, gallery)

The system is ready for integration testing and deployment.

### Post-Implementation Steps

1. Run full test suite (backend + frontend)
2. Deploy to staging environment
3. Perform manual E2E testing
4. Update user documentation
5. Deploy to production
