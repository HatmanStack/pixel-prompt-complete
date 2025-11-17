/**
 * Parameter Presets
 * Pre-configured parameter combinations for common use cases
 */

export const presets = [
  {
    name: 'Fast',
    description: 'Quick generation with lower quality',
    icon: '⚡',
    steps: 15,
    guidance: 5,
    control: 1.0,
  },
  {
    name: 'Quality',
    description: 'High quality images (slower generation)',
    icon: '✨',
    steps: 50,
    guidance: 10,
    control: 1.5,
  },
  {
    name: 'Creative',
    description: 'More artistic freedom and variation',
    icon: '🎨',
    steps: 25,
    guidance: 3,
    control: 0.5,
  },
];

/**
 * Get preset by name
 * @param {string} name - Preset name
 * @returns {Object|null} Preset configuration or null if not found
 */
export function getPresetByName(name) {
  return presets.find(p => p.name === name) || null;
}

/**
 * Check if current parameters match a preset
 * @param {number} steps - Current steps value
 * @param {number} guidance - Current guidance value
 * @param {number} control - Current control value
 * @returns {Object|null} Matching preset or null
 */
export function getActivePreset(steps, guidance, control) {
  return presets.find(
    p => p.steps === steps && p.guidance === guidance && p.control === control
  ) || null;
}

export default presets;
