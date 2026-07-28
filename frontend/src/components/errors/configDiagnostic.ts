/**
 * The screen shown when the build's own configuration is broken.
 *
 * Deliberately plain DOM: no React, no Tailwind, no imports beyond this file.
 * This runs when `api/config.ts` found the app misconfigured, and a
 * diagnostic that depends on the app is not a diagnostic — if the reason the
 * app cannot start is a missing endpoint, a renderer that needs the app's
 * bundle to work has a decent chance of failing for the same reason.
 *
 * It lives in its own module rather than inline in `main.tsx` because
 * `main.tsx` is excluded from coverage (`vite.config.ts`), and an untested
 * diagnostic is a diagnostic nobody has ever seen.
 */

const PANEL_STYLE = [
  'max-width:44rem',
  'margin:4rem auto',
  'padding:1.5rem',
  'border:2px solid #b3261e',
  'border-radius:0.5rem',
  'background:#fff',
  'color:#1b1b1b',
  'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif',
  'line-height:1.5',
].join(';');

/**
 * Render `errors` into `element`, replacing its contents.
 *
 * Text is set with `textContent`, never `innerHTML`: these strings are
 * assembled from environment variables, which are build inputs, and a
 * diagnostic page is not a place to introduce an injection sink.
 */
export function renderConfigDiagnostic(errors: string[], element: HTMLElement): void {
  element.textContent = '';

  const panel = document.createElement('div');
  panel.setAttribute('role', 'alert');
  panel.setAttribute('data-testid', 'config-diagnostic');
  panel.setAttribute('style', PANEL_STYLE);

  const heading = document.createElement('h1');
  heading.textContent = 'Configuration error';
  heading.setAttribute('style', 'margin:0 0 0.5rem;font-size:1.25rem');

  const intro = document.createElement('p');
  intro.textContent =
    'This build is missing configuration it needs, so the app has not been started. ' +
    'Set the variables below and rebuild.';
  intro.setAttribute('style', 'margin:0 0 1rem');

  const list = document.createElement('ul');
  list.setAttribute('style', 'margin:0;padding-left:1.25rem');
  for (const error of errors) {
    const item = document.createElement('li');
    item.textContent = error;
    list.appendChild(item);
  }

  panel.append(heading, intro, list);
  element.appendChild(panel);
}

export default renderConfigDiagnostic;
