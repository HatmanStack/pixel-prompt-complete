# Pixel Prompt Complete - Frontend

Modern React frontend for the Pixel Prompt text-to-image generation platform.

## Features

- **Vite React** - Fast development with HMR
- **Dynamic Model Support** - Works with variable model counts (3, 9, 20+ models)
- **Real-time Updates** - Progressive image loading via job polling
- **Gallery Browser** - Browse historical generations
- **Prompt Enhancement** - LLM-powered prompt improvement
- **Responsive Design** - Mobile and desktop optimized
- **Accessible** - WCAG AA compliant

## Prerequisites

- Node.js 18+
- npm or yarn
- Backend deployed and accessible

## Development Setup

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and set VITE_API_ENDPOINT to your API Gateway URL
   ```

3. **Start development server:**
   ```bash
   npm run dev
   ```
   Access at http://localhost:3000

## Available Scripts

- `npm run dev` - Start development server (port 3000)
- `npm run build` - Build production bundle
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint

## Environment Variables

Create `.env` file with:

```bash
VITE_API_ENDPOINT=https://your-api-endpoint.execute-api.us-west-2.amazonaws.com/Prod
```

## Project Structure

```
src/
├── api/              # API client and fetch utilities
├── components/       # React components
│   ├── common/       # Generic components (buttons, inputs)
│   ├── gallery/      # Gallery-related components
│   └── generation/   # Image generation components
├── hooks/            # Custom React hooks
├── utils/            # Helper functions
├── assets/           # Images, fonts, sounds
│   ├── images/
│   ├── fonts/
│   └── sounds/
├── styles/           # CSS files
├── App.jsx           # Root component
└── main.jsx          # Entry point
```

## Coding Conventions

### Component Naming
- **Files:** PascalCase matching component name (`PromptInput.jsx`)
- **Components:** PascalCase function components
- **Props:** camelCase with destructuring

Example:
```javascript
function PromptInput({ value, onChange, maxLength }) {
  // ...
}
```

### Hook Naming
- **Files:** camelCase with `use` prefix (`useJobPolling.js`)
- **Hooks:** Start with `use` prefix

Example:
```javascript
function useJobPolling(jobId, interval = 2000) {
  // ...
}
```

### Styling
- **CSS Modules:** `ComponentName.module.css`
- **Import:** `import styles from './ComponentName.module.css'`
- **Usage:** `<div className={styles.container}>`

### State Management
- Local state: `useState` for component-specific state
- Global state: React Context via `AppContext`
- Derived state: `useMemo` for expensive calculations

## Code Organization Guidelines

1. **One component per file**
2. **Group related components** in subdirectories
3. **Export at bottom** of file for components
4. **Imports order:**
   - React imports
   - Third-party imports
   - Internal imports (utils, hooks)
   - Styles

5. **Props destructuring** in function signature
6. **Early returns** for conditional rendering

## Building for Production

```bash
npm run build
```

Output in `dist/` directory. Deploy to:
- AWS S3 + CloudFront
- Netlify
- Vercel
- Any static hosting

## Performance Best Practices

- Use `React.memo` for expensive components
- Lazy load heavy components with `React.lazy`
- Optimize images (compress, WebP)
- Code split with dynamic imports
- Minimize bundle size (check with `npm run build`)

## Accessibility

- Semantic HTML elements
- ARIA labels on interactive elements
- Keyboard navigation support
- Focus management
- Screen reader tested
- Color contrast WCAG AA

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Troubleshooting

### Dev server won't start
- Check port 3000 is not in use
- Verify Node.js version >= 18
- Delete `node_modules` and run `npm install`

### Build fails
- Clear cache: `rm -rf node_modules dist .vite`
- Reinstall: `npm install`
- Check for ESLint errors: `npm run lint`

### API calls failing
- Verify `VITE_API_ENDPOINT` in `.env`
- Check CORS settings on backend
- Verify backend is deployed and accessible
- Check browser DevTools Network tab

## Contributing

1. Follow coding conventions
2. Run `npm run lint` before committing
3. Test on mobile and desktop
4. Ensure accessibility standards

## License

See root LICENSE file
