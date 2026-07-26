/**
 * Deploy parameter tests.
 *
 * deploy.js had no tests, and had drifted far enough to break the deploy: it
 * passed FluxEnabled, RecraftEnabled and their API keys, which are not
 * parameters in this template, and never passed AuthEnabled, which is
 * required. CloudFormation rejects unknown parameters, so the whole deploy
 * would have failed at the first attempt.
 *
 * The important test here is the last one: every parameter this script sends
 * must exist in template.yaml.
 *
 * Lives under frontend/tests because that is where CI runs vitest. deploy.js
 * is repo-level tooling, but a test CI never executes is worth nothing.
 */

/* global process */
import { describe, it, expect, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { buildParameterOverrides } from '../../../../backend/scripts/deploy.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TEMPLATE = path.join(__dirname, '..', '..', '..', '..', 'backend', 'template.yaml');

function config(overrides = {}) {
  return {
    authEnabled: 'false',
    alarmEmail: '',
    spend: { monthlyCeilingUsdMicros: '', dailyCeilingUsdMicros: '' },
    promptModel: { provider: 'openai', id: 'gpt-4o', apiKey: '' },
    models: {
      gemini: { enabled: true, apiKey: '', modelId: '' },
      nova: { enabled: true, modelId: '' },
      openai: { enabled: true, apiKey: '', modelId: '' },
      firefly: { enabled: true, clientId: '', clientSecret: '', modelId: '' },
    },
    ...overrides,
  };
}

function keysOf(overrides) {
  return overrides.map((o) => o.split('=')[0]);
}

/** Parameter names declared in template.yaml. */
function templateParameters() {
  const text = readFileSync(TEMPLATE, 'utf8');
  const start = text.indexOf('\nParameters:');
  const end = text.indexOf('\nConditions:');
  const block = text.slice(start, end > start ? end : undefined);
  return new Set([...block.matchAll(/^ {2}([A-Za-z][A-Za-z0-9]*):$/gm)].map((m) => m[1]));
}

describe('buildParameterOverrides', () => {
  it('always passes AuthEnabled, which the template requires', () => {
    expect(keysOf(buildParameterOverrides(config()))).toContain('AuthEnabled');
  });

  it('refuses to deploy when AUTH_ENABLED is unset', () => {
    // There is no safe default. Guessing picks a security posture for the
    // operator, which is how a stack ends up open because nobody decided.
    const exit = vi.spyOn(process, 'exit').mockImplementation(() => {
      throw new Error('exited');
    });
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => buildParameterOverrides(config({ authEnabled: undefined }))).toThrow();
    expect(exit).toHaveBeenCalledWith(1);
    vi.restoreAllMocks();
  });

  it('refuses a value that is neither true nor false', () => {
    vi.spyOn(process, 'exit').mockImplementation(() => {
      throw new Error('exited');
    });
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => buildParameterOverrides(config({ authEnabled: 'yes' }))).toThrow();
    vi.restoreAllMocks();
  });

  it('passes all four real models', () => {
    const keys = keysOf(buildParameterOverrides(config()));
    for (const k of ['GeminiEnabled', 'NovaEnabled', 'OpenaiEnabled', 'FireflyEnabled']) {
      expect(keys).toContain(k);
    }
  });

  it('does not pass models this stack no longer has', () => {
    const keys = keysOf(buildParameterOverrides(config()));
    for (const k of keys) {
      expect(k).not.toMatch(/Flux|Recraft/);
    }
  });

  it('omits credentials that are not configured', () => {
    const keys = keysOf(buildParameterOverrides(config()));
    expect(keys).not.toContain('GeminiApiKey');
    expect(keys).not.toContain('FireflyClientSecret');
  });

  it('passes credentials that are configured', () => {
    const c = config();
    c.models.gemini.apiKey = 'k';
    c.models.firefly.clientSecret = 's';
    const keys = keysOf(buildParameterOverrides(c));
    expect(keys).toContain('GeminiApiKey');
    expect(keys).toContain('FireflyClientSecret');
  });

  it('omits model ids so template defaults stay authoritative', () => {
    // Passing an empty string would shadow the default with nothing.
    expect(keysOf(buildParameterOverrides(config()))).not.toContain('GeminiModelId');
  });

  it('passes spend ceilings and alarm email only when set', () => {
    const bare = keysOf(buildParameterOverrides(config()));
    expect(bare).not.toContain('AlarmEmail');
    expect(bare).not.toContain('MonthlySpendCeilingUsdMicros');

    const set = keysOf(
      buildParameterOverrides(
        config({
          alarmEmail: 'ops@example.com',
          spend: { monthlyCeilingUsdMicros: '500000000', dailyCeilingUsdMicros: '25000000' },
        }),
      ),
    );
    expect(set).toContain('AlarmEmail');
    expect(set).toContain('MonthlySpendCeilingUsdMicros');
    expect(set).toContain('GlobalDailySpendCeilingUsdMicros');
  });

  it('sends no parameter that the template does not declare', () => {
    // The check that would have caught the Flux/Recraft drift. CloudFormation
    // rejects unknown parameters outright, failing the entire deploy.
    const declared = templateParameters();
    const c = config({
      alarmEmail: 'ops@example.com',
      spend: { monthlyCeilingUsdMicros: '1', dailyCeilingUsdMicros: '2' },
    });
    c.promptModel.apiKey = 'k';
    c.models.gemini.apiKey = 'k';
    c.models.gemini.modelId = 'm';
    c.models.nova.modelId = 'm';
    c.models.openai.apiKey = 'k';
    c.models.openai.modelId = 'm';
    c.models.firefly.clientId = 'i';
    c.models.firefly.clientSecret = 's';
    c.models.firefly.modelId = 'm';

    const unknown = keysOf(buildParameterOverrides(c)).filter((k) => !declared.has(k));
    expect(unknown).toEqual([]);
  });
});
