/**
 * AuthCallback page.
 * Parses `?code=` from the URL, exchanges it for Cognito tokens, stores them
 * in useAuthStore, and redirects home.
 */

import { useEffect, useState, type FC } from 'react';
import { exchangeCodeForTokens } from '@/api/cognito';
import { useAuthStore } from '@/stores/useAuthStore';

export const AuthCallback: FC = () => {
  const [error, setError] = useState<string | null>(null);
  const setTokens = useAuthStore((s) => s.setTokens);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    if (!code) {
      setError('Missing authorization code.');
      return;
    }
    exchangeCodeForTokens(code)
      .then((tokens) => {
        setTokens(tokens);
        window.location.replace('/');
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Sign-in failed.');
      });
  }, [setTokens]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6 text-center">
      {error ? (
        <div>
          <p className="text-red-500 mb-2">Sign-in failed</p>
          <p className="text-sm text-gray-400">{error}</p>
          <a href="/" className="underline text-accent">
            Return home
          </a>
        </div>
      ) : (
        <p>Signing you in...</p>
      )}
    </div>
  );
};

export default AuthCallback;
