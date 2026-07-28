/**
 * 18+ confirmation, shown when the backend refuses a generation with
 * AGE_VERIFICATION_REQUIRED.
 *
 * Deliberately reactive rather than a splash screen on first visit. The server
 * is the thing that knows whether this identity has already answered, so
 * letting it say "ask them" keeps one source of truth and means clearing
 * localStorage does not silently skip the gate.
 *
 * Presented neutrally: no default selection, and declining is a real option
 * with equal weight. A gate that nudges toward "yes" is worse evidence than
 * one that does not, since the point is to show we asked honestly.
 */

import { useEffect, useRef } from 'react';

interface AgeGateModalProps {
  open: boolean;
  onConfirm: () => void;
  onDecline: () => void;
}

export function AgeGateModal({ open, onConfirm, onDecline }: AgeGateModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  // `aria-modal="true"` is a promise to assistive technology that nothing
  // outside this dialog is reachable. Without focus management it is simply
  // untrue: focus stays wherever it was, Tab walks straight out into the page
  // behind, and a screen-reader user is told they are in a modal while
  // reading content the modal claims to have sealed off.
  //
  // Deliberately no Escape handler. Every other dialog here closes on Escape,
  // but this one has no neutral dismissal -- the two answers are "18 or over"
  // and "under 18", and treating a keypress as either would be recording an
  // answer the user did not give.
  useEffect(() => {
    if (!open) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const focusables = () =>
      Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.hasAttribute('disabled'));

    // The decline button, not the affirm one. Focusing "I am 18 or older"
    // would put the affirmative answer one Enter away from a user who has not
    // read the question, which is the nudge this dialog's copy avoids.
    const initial = focusables();
    initial[initial.length - 1]?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const els = focusables();
      if (els.length === 0) return;
      const first = els[0];
      const last = els[els.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      // Hand focus back where it was, so dismissing the gate does not dump a
      // keyboard user at the top of the document.
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="age-gate-title"
      aria-describedby="age-gate-body"
    >
      <div className="w-full max-w-md rounded-lg bg-neutral-900 p-6 text-neutral-100 shadow-xl">
        <h2 id="age-gate-title" className="text-lg font-semibold">
          Confirm your age
        </h2>

        <p id="age-gate-body" className="mt-3 text-sm text-neutral-300">
          This service is only available to people aged 18 or over. The AI providers it runs on
          require it.
        </p>

        <div className="mt-6 flex flex-col gap-2 sm:flex-row-reverse">
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white"
          >
            I am 18 or older
          </button>
          <button
            type="button"
            onClick={onDecline}
            className="rounded-md border border-neutral-700 px-4 py-2 text-sm font-medium text-neutral-300 hover:bg-neutral-800"
          >
            I am under 18
          </button>
        </div>
      </div>
    </div>
  );
}

export default AgeGateModal;
