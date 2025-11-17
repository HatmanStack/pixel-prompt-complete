# Testing Guide - Pixel Prompt Complete Frontend

Comprehensive testing documentation for the React frontend.

## Overview

The frontend includes 122 unit tests and 23 integration tests covering all React components and user workflows.

## Running Tests

### All Tests

```bash
cd frontend
npm test
```

### Watch Mode (Auto-rerun on Changes)

```bash
npm test -- --watch
```

### Specific Test File

```bash
npm test -- src/__tests__/components/PromptInput.test.jsx
```

### With Coverage

```bash
npm test -- --coverage
```

Open coverage report:
```bash
open coverage/index.html
```

### UI Mode (Interactive Test Explorer)

```bash
npm run test:ui
```

## Test Organization

```
frontend/src/__tests__/
├── components/               # Component unit tests (61 tests)
│   ├── PromptInput.test.jsx           # Text input with validation
│   ├── ParameterSliders.test.jsx      # Range controls
│   ├── ImageCard.test.jsx             # Image display with modal
│   ├── GenerateButton.test.jsx        # Generation trigger
│   ├── PromptEnhancer.test.jsx        # AI prompt enhancement
│   ├── ImageGrid.test.jsx             # Gallery display
│   ├── GalleryBrowser.test.jsx        # Gallery navigation
│   └── GalleryPreview.test.jsx        # Gallery thumbnails
├── integration/              # Integration tests (23 tests)
│   ├── generateFlow.test.jsx          # Full generation workflow
│   ├── galleryFlow.test.jsx           # Gallery loading/display
│   ├── enhanceFlow.test.jsx           # Prompt enhancement flow
│   └── errorHandling.test.jsx         # Error scenarios
└── fixtures/
    └── apiResponses.js                # Mock API data
```

## Test Coverage

### Component Tests (122 total)

**Core Components (61 tests)**:
- **PromptInput** (13 tests): Text entry, validation, character counting
- **ParameterSliders** (13 tests): Range controls, rounding, edge values
- **ImageCard** (15 tests): Image display, modal, download, error states
- **GenerateButton** (20 tests): State management, loading, error handling

**Feature Components (61 tests)**:
- **PromptEnhancer** (14 tests): API integration, loading states, error recovery
- **ImageGrid** (13 tests): Grid layout, empty states, modal interactions
- **GalleryBrowser** (20 tests): Gallery listing, loading, selection
- **GalleryPreview** (14 tests): Thumbnails, metadata, keyboard support

### Integration Tests (23 tests)

**User Workflows**:
- **Generate Flow** (7 tests): Complete image generation from prompt to results
- **Gallery Flow** (6 tests): Loading and displaying gallery contents
- **Enhance Flow** (5 tests): Prompt enhancement and usage
- **Error Handling** (5 tests): Network errors, validation, recovery

## Testing Technologies

- **Vitest**: Fast Vite-native test runner
- **React Testing Library**: Component testing utilities
- **@testing-library/user-event**: Realistic user interactions
- **jsdom**: Browser environment simulation

## Writing Tests

### Component Test Example

```javascript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import MyComponent from '../components/MyComponent';

describe('MyComponent', () => {
  it('handles user interaction', async () => {
    const user = userEvent.setup();
    const mockCallback = vi.fn();

    render(<MyComponent onClick={mockCallback} />);

    await user.click(screen.getByRole('button'));

    expect(mockCallback).toHaveBeenCalled();
  });
});
```

### Integration Test Example

```javascript
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import * as apiClient from '../api/client';
import App from '../App';

vi.mock('../api/client');

describe('Full Workflow', () => {
  it('completes generation flow', async () => {
    apiClient.generateImages.mockResolvedValue({ jobId: 'test-123' });

    render(<App />);

    // Test user workflow...
    await waitFor(() => {
      expect(screen.getByText('Generated!')).toBeInTheDocument();
    });
  });
});
```

## Test Commands Reference

| Command | Description |
|---------|-------------|
| `npm test` | Run all tests once |
| `npm test -- --watch` | Watch mode (re-run on changes) |
| `npm test -- --ui` | Interactive UI mode |
| `npm test -- --coverage` | Run with coverage report |
| `npm test -- --reporter=verbose` | Detailed test output |
| `npm test -- --run` | Run once without watch (CI mode) |

## Configuration

Tests are configured in `vite.config.js`:

```javascript
export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.js',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/**/*.test.{js,jsx}', 'src/main.jsx']
    }
  }
});
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Frontend Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: cd frontend && npm ci
      - run: cd frontend && npm test -- --run
      - run: cd frontend && npm test -- --coverage --run
```

## Troubleshooting

### Tests Failing Locally

**Issue**: Tests pass in CI but fail locally
```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
npm test
```

**Issue**: "Cannot find module" errors
```bash
# Verify all dependencies installed
npm install
```

**Issue**: Async test timeouts
```javascript
// Increase timeout for slow tests
it('slow test', async () => {
  // test code
}, 15000); // 15 second timeout
```

### Common Test Patterns

**Testing async state changes**:
```javascript
await waitFor(() => {
  expect(screen.getByText('Loaded')).toBeInTheDocument();
});
```

**Testing user interactions**:
```javascript
const user = userEvent.setup();
await user.click(screen.getByRole('button'));
await user.type(screen.getByRole('textbox'), 'test input');
```

**Mocking API calls**:
```javascript
vi.mock('../api/client');
apiClient.generateImages.mockResolvedValue({ jobId: '123' });
```

## Best Practices

1. **Use Testing Library queries by priority**:
   - `getByRole` (most accessible)
   - `getByLabelText`
   - `getByPlaceholderText`
   - `getByText`
   - `getByTestId` (last resort)

2. **Test user behavior, not implementation**:
   ```javascript
   // ✅ Good - tests behavior
   await user.click(screen.getByRole('button', { name: /generate/i }));
   expect(screen.getByText('Loading...')).toBeInTheDocument();

   // ❌ Bad - tests implementation
   expect(component.state.loading).toBe(true);
   ```

3. **Use userEvent over fireEvent**:
   ```javascript
   // ✅ Good - realistic user interaction
   const user = userEvent.setup();
   await user.click(button);

   // ❌ Bad - low-level event
   fireEvent.click(button);
   ```

4. **Clean up properly**:
   ```javascript
   beforeEach(() => {
     vi.clearAllMocks();
   });
   ```

## Performance

- **Test suite execution**: ~5-10 seconds for all tests
- **Watch mode**: Hot reload on file changes
- **Coverage generation**: Adds ~2-3 seconds

## Next Steps

After tests are passing:
1. ✅ Verify coverage meets targets (>60%)
2. ✅ Add tests for new components
3. ✅ Run tests in CI pipeline
4. ✅ Monitor test performance

## Support

For test-related issues:
- Check [Vitest documentation](https://vitest.dev/)
- Check [Testing Library docs](https://testing-library.com/react)
- Review existing test examples in `src/__tests__/`
