/**
 * ParameterPresets Component
 * Preset buttons for common parameter configurations
 * Fast, Quality, Creative modes
 */

import { presets, getActivePreset } from '../../../data/presets';
import styles from './ParameterPresets.module.css';

function ParameterPresets({ steps, guidance, control, onPresetSelect, disabled = false }) {
  const activePreset = getActivePreset(steps, guidance, control);

  const handlePresetClick = (preset) => {
    if (disabled) return;

    onPresetSelect({
      steps: preset.steps,
      guidance: preset.guidance,
      control: preset.control,
    });
  };

  return (
    <div className={styles.container}>
      <label className={styles.label}>Presets:</label>
      <div className={styles.presets}>
        {presets.map((preset) => {
          const isActive = activePreset?.name === preset.name;

          return (
            <button
              key={preset.name}
              className={`${styles.preset} ${isActive ? styles.active : ''}`}
              onClick={() => handlePresetClick(preset)}
              disabled={disabled}
              aria-label={`${preset.name} preset: ${preset.description}`}
              title={`${preset.description}\nSteps: ${preset.steps}, Guidance: ${preset.guidance}, Control: ${preset.control}`}
            >
              <span className={styles.icon}>{preset.icon}</span>
              <span className={styles.name}>{preset.name}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default ParameterPresets;
