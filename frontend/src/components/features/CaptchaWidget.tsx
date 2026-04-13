/**
 * CaptchaWidget - Cloudflare Turnstile CAPTCHA wrapper.
 * Renders only when CAPTCHA_ENABLED is true and user is not authenticated.
 * Dynamically loads the Turnstile script and renders the widget.
 */

import { useEffect, useRef, useCallback, type FC } from 'react';
import { CAPTCHA_ENABLED, TURNSTILE_SITE_KEY } from '@/api/config';
import { useAuthStore } from '@/stores/useAuthStore';

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement,
        opts: { sitekey: string; callback: (token: string) => void },
      ) => string;
      reset: (widgetId: string) => void;
      remove: (widgetId: string) => void;
    };
  }
}

interface CaptchaWidgetProps {
  onVerify: (token: string) => void;
  /** Called with a reset function that the parent can invoke to reset the widget */
  onReset?: (resetFn: () => void) => void;
}

const TURNSTILE_SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js';

function loadTurnstileScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.turnstile) {
      resolve();
      return;
    }
    const existing = document.querySelector(`script[src="${TURNSTILE_SCRIPT_URL}"]`);
    if (existing) {
      existing.addEventListener('load', () => resolve());
      return;
    }
    const script = document.createElement('script');
    script.src = TURNSTILE_SCRIPT_URL;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Turnstile script'));
    document.head.appendChild(script);
  });
}

export const CaptchaWidget: FC<CaptchaWidgetProps> = ({ onVerify, onReset }) => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);

  const reset = useCallback(() => {
    if (window.turnstile && widgetIdRef.current) {
      window.turnstile.reset(widgetIdRef.current);
    }
  }, []);

  useEffect(() => {
    if (onReset) {
      onReset(reset);
    }
  }, [onReset, reset]);

  useEffect(() => {
    if (!CAPTCHA_ENABLED || isAuthenticated || !containerRef.current) return;

    let mounted = true;

    const init = async () => {
      await loadTurnstileScript();
      if (!mounted || !containerRef.current || !window.turnstile) return;

      widgetIdRef.current = window.turnstile.render(containerRef.current, {
        sitekey: TURNSTILE_SITE_KEY,
        callback: (token: string) => {
          onVerify(token);
        },
      });
    };

    init();

    return () => {
      mounted = false;
      if (window.turnstile && widgetIdRef.current) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
    };
  }, [isAuthenticated, onVerify]);

  if (!CAPTCHA_ENABLED || isAuthenticated) {
    return null;
  }

  return <div ref={containerRef} data-testid="captcha-container" />;
};
