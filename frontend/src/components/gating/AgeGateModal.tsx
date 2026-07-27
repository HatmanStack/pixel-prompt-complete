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

interface AgeGateModalProps {
  open: boolean;
  onConfirm: () => void;
  onDecline: () => void;
}

export function AgeGateModal({ open, onConfirm, onDecline }: AgeGateModalProps) {
  if (!open) return null;

  return (
    <div
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
