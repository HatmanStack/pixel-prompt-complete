# Pixel Prompt v2: Focused Multi-Model Image Generation with Iterative Refinement

## Feature Overview

This plan transforms Pixel Prompt Complete from a dynamic N-model image generation platform into a focused 4-model system with conversational image iteration capabilities. The redesigned application generates images from four specific AI providers (Flux, Recraft, Google Gemini "Nano Banana", and OpenAI gpt-image-1) displayed in a horizontal row, with each image column supporting up to 7 iterations of conversational refinement.

The core user experience shifts from "generate once, view results" to "generate, then iteratively refine each image through conversation." Users can select one or multiple images via checkbox overlays and apply refinement prompts that leverage rolling 3-iteration context windows. Each provider's unique editing capabilities (inpainting, outpainting, image-to-image) are abstracted behind a unified iteration API, allowing users to request changes like "make the sky more purple" or expand images using aspect ratio presets (16:9, 9:16, 1:1, 4:3, Expand All).

The gallery system groups images by original prompt with iterations nested underneath, enabling users to browse their generation history and revisit previous creative sessions. The entire backend is simplified from 20 dynamic model slots to 4 fixed models with enable/disable flags and version-swappable configurations.

## Prerequisites

### Development Environment
- **Node.js**: v20+ LTS (managed via nvm)
- **Python**: 3.12+ (managed via uv)
- **AWS CLI**: v2+ configured with credentials
- **AWS SAM CLI**: v1.100+
- **Git**: v2.30+

### Required API Keys (stored in `.env.deploy`)
- **OpenAI**: Organization-verified account with gpt-image-1 access
- **Google AI**: Gemini API key with image generation enabled
- **Black Forest Labs**: BFL API key for Flux models
- **Recraft**: Recraft v3 API key

### AWS Resources (created by SAM)
- Lambda function (Python 3.12 runtime)
- API Gateway (HTTP API)
- S3 bucket for image/job storage
- CloudFront distribution for CDN delivery
- CloudWatch logs and alarms

## Phase Summary

| Phase | Goal | Estimated Tokens | Key Deliverables |
|-------|------|------------------|------------------|
| **Phase 0** | Foundation & Standards | ~15,000 | ADRs, deploy script specs, testing strategy, shared patterns |
| **Phase 1** | Backend Transformation | ~45,000 | 4 fixed models, iteration endpoints, conversation context, outpainting |
| **Phase 2** | Frontend Redesign | ~40,000 | Column layout, iteration UI, multi-select, gallery reorganization |

**Total Estimated Tokens**: ~100,000 (fits in single context window)

## Navigation

- [Phase 0: Foundation & Standards](./Phase-0.md)
- [Phase 1: Backend Transformation](./Phase-1.md)
- [Phase 2: Frontend Redesign](./Phase-2.md)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React + Vite)                        │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   FLUX      │  │  RECRAFT    │  │   GEMINI    │  │   OPENAI    │    │
│  │  Column     │  │  Column     │  │  Column     │  │  Column     │    │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤  ├─────────────┤    │
│  │ [Original]  │  │ [Original]  │  │ [Original]  │  │ [Original]  │    │
│  │ [Iter 1]    │  │ [Iter 1]    │  │ [Iter 1]    │  │ [Iter 1]    │    │
│  │ [Iter 2]    │  │ [Iter 2]    │  │ [Iter 2]    │  │ [Iter 2]    │    │
│  │    ...      │  │    ...      │  │    ...      │  │    ...      │    │
│  │ [Iter 7]    │  │ [Iter 7]    │  │ [Iter 7]    │  │ [Iter 7]    │    │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤  ├─────────────┤    │
│  │ [Prompt]    │  │ [Prompt]    │  │ [Prompt]    │  │ [Prompt]    │    │
│  │ [Outpaint]  │  │ [Outpaint]  │  │ [Outpaint]  │  │ [Outpaint]  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    GALLERY (Grouped by Prompt)                   │   │
│  │  [Session 1] ─► Original + Iterations                           │   │
│  │  [Session 2] ─► Original + Iterations                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ API Gateway
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        BACKEND (AWS Lambda + SAM)                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  POST /generate          ─► Generate initial 4 images                   │
│  POST /iterate           ─► Iterate on specific image(s)                │
│  POST /outpaint          ─► Expand image with aspect preset             │
│  GET  /status/{jobId}    ─► Poll job status                             │
│  GET  /gallery/list      ─► List sessions by prompt                     │
│  GET  /gallery/{id}      ─► Get session with iterations                 │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      MODEL HANDLERS                               │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐             │  │
│  │  │  Flux   │  │ Recraft │  │ Gemini  │  │ OpenAI  │             │  │
│  │  │ (BFL)   │  │  (v3)   │  │ (Nano)  │  │(gpt-img)│             │  │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘             │  │
│  │       │            │            │            │                   │  │
│  │       ▼            ▼            ▼            ▼                   │  │
│  │  generate()   generate()   generate()   generate()               │  │
│  │  iterate()    iterate()    iterate()    iterate()                │  │
│  │  outpaint()   outpaint()   outpaint()   outpaint()               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    CONVERSATION CONTEXT                           │  │
│  │  Rolling 3-iteration window per image column                      │  │
│  │  Stored in S3: sessions/{sessionId}/context/{model}.json          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              AWS RESOURCES                               │
├─────────────────────────────────────────────────────────────────────────┤
│  S3 Bucket                                                              │
│  ├── sessions/{sessionId}/                                              │
│  │   ├── status.json              (session metadata)                    │
│  │   ├── context/                                                       │
│  │   │   ├── flux.json            (conversation history)                │
│  │   │   ├── recraft.json                                               │
│  │   │   ├── gemini.json                                                │
│  │   │   └── openai.json                                                │
│  │   └── images/                                                        │
│  │       ├── flux-0.png           (original)                            │
│  │       ├── flux-1.png           (iteration 1)                         │
│  │       └── ...                                                        │
│  └── gallery/                     (index for browsing)                  │
│                                                                         │
│  CloudFront ─► CDN for image delivery                                   │
│  CloudWatch ─► Logs and alarms                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **4 Fixed Models**: Simplifies configuration, deployment, and UI design
2. **Session-Based Storage**: Each generation session is self-contained with its iterations
3. **Rolling Context Window**: Last 3 iterations sent to model for conversational refinement
4. **Provider-Specific Handlers**: Each provider implements generate(), iterate(), outpaint()
5. **Unified Outpaint API**: Aspect presets translated to provider-specific mask/params
6. **Per-Column Input**: Each model column has its own prompt input for independent iteration
7. **Multi-Select Override**: Checkbox selection allows applying one prompt to multiple columns

## File Organization

```
pixel-prompt-complete/
├── backend/
│   ├── src/
│   │   ├── lambda_function.py      # Route handlers
│   │   ├── config.py               # 4-model configuration
│   │   ├── models/
│   │   │   ├── registry.py         # Fixed model registry
│   │   │   ├── handlers.py         # Provider handlers (generate/iterate/outpaint)
│   │   │   └── context.py          # Conversation context management
│   │   ├── jobs/
│   │   │   ├── manager.py          # Session/job lifecycle
│   │   │   └── executor.py         # Parallel execution
│   │   └── utils/
│   │       └── outpaint.py         # Aspect preset calculations
│   ├── scripts/
│   │   └── deploy.js               # Enhanced deployment script
│   └── template.yaml               # Simplified SAM template
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── generation/
│   │   │   │   ├── GenerationPanel.tsx    # Main orchestrator
│   │   │   │   ├── ModelColumn.tsx        # Single model column
│   │   │   │   ├── IterationCard.tsx      # Image + metadata
│   │   │   │   ├── IterationInput.tsx     # Per-column prompt input
│   │   │   │   └── OutpaintControls.tsx   # Aspect presets
│   │   │   └── gallery/
│   │   │       ├── GalleryBrowser.tsx     # Session list
│   │   │       └── SessionView.tsx        # Expanded session
│   │   ├── stores/
│   │   │   └── useAppStore.ts             # Zustand state
│   │   ├── hooks/
│   │   │   ├── useSessionPolling.ts       # Poll session status
│   │   │   └── useIteration.ts            # Iteration logic
│   │   └── api/
│   │       └── client.ts                  # API methods
│   └── tests/
│       └── __tests__/                     # Vitest tests
└── docs/
    └── plans/
        ├── README.md                      # This file
        ├── Phase-0.md                     # Foundation
        ├── Phase-1.md                     # Backend
        └── Phase-2.md                     # Frontend
```
