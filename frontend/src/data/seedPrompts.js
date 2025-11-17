/**
 * Seed Prompts Collection
 * Creative prompt examples to inspire users
 * Categorized by style for variety
 */

export const seedPrompts = [
  // Landscapes & Nature (15)
  'A serene mountain lake at sunset with reflections',
  'Cherry blossom trees in full bloom along a winding path',
  'Northern lights dancing over a frozen tundra',
  'Misty forest with rays of sunlight breaking through',
  'Desert sand dunes under a starry night sky',
  'Tropical waterfall cascading into a crystal-clear pool',
  'Autumn forest with vibrant red and orange leaves',
  'Snow-covered peaks reflected in an alpine lake',
  'Coastal cliffs at sunrise with crashing waves',
  'Rolling green hills dotted with wildflowers',
  'Ancient redwood forest with towering trees',
  'Volcanic landscape with flowing lava at dusk',
  'Peaceful bamboo forest with filtered sunlight',
  'Canyon walls glowing in golden hour light',
  'Glacial ice cave with blue and white formations',

  // Urban & Architecture (10)
  'Cyberpunk city street with neon signs in the rain',
  'Modern minimalist architecture with clean lines',
  'Gothic cathedral interior with stained glass windows',
  'Bustling Tokyo street at night with bright billboards',
  'Art deco building facade in pastel colors',
  'Futuristic cityscape with flying vehicles',
  'Cozy European alleyway with cafe tables',
  'Abandoned industrial warehouse overtaken by nature',
  'Sleek modern library with floor-to-ceiling windows',
  'Victorian-era street with gas lamps and cobblestones',

  // Fantasy & Sci-Fi (15)
  'Ethereal floating islands in the clouds',
  'Dragon perched on a medieval castle tower',
  'Spacecraft approaching a distant nebula',
  'Crystal cave glowing with magical light',
  'Steampunk airship soaring through clouds',
  'Portal to another dimension opening in space',
  'Ancient wizard tower surrounded by mystical fog',
  'Alien landscape with bioluminescent plants',
  'Mechanical robot tending a zen garden',
  'Enchanted library with floating books',
  'Space station orbiting a ringed planet',
  'Mythical phoenix rising from ashes',
  'Underground dwarven city carved in stone',
  'Time traveler stepping through a glowing portal',
  'Giant mushroom forest in an alien world',

  // Art Styles (10)
  'Watercolor painting of a flower garden in spring',
  'Abstract geometric shapes in bold colors',
  'Oil painting of a stormy ocean',
  'Minimalist line drawing of a dancer',
  'Pop art style portrait with vibrant colors',
  'Impressionist cafe scene with soft brush strokes',
  'Digital glitch art with fragmented patterns',
  'Art nouveau poster with flowing organic forms',
  'Cubist interpretation of a cityscape',
  'Surrealist dreamscape with melting clocks',

  // Characters & Portraits (10)
  'Wise old wizard with flowing robes and staff',
  'Cybernetic warrior in futuristic armor',
  'Elegant ballroom dancer mid-twirl',
  'Mysterious masked figure in Venice carnival',
  'Young astronaut looking out spaceship window',
  'Medieval knight in shining armor at sunset',
  'Jazz musician playing saxophone in smoky club',
  'Ethereal forest spirit with glowing eyes',
  'Steampunk inventor in workshop full of gadgets',
  'Ancient samurai in traditional garb',

  // Animals & Creatures (10)
  'Majestic lion resting in golden savanna grass',
  'Colorful tropical fish in coral reef',
  'Owl with piercing eyes perched on branch',
  'Butterflies emerging from chrysalis',
  'Dolphin leaping through ocean waves',
  'Arctic fox in snowy landscape',
  'Peacock displaying vibrant tail feathers',
  'Wolf howling at full moon',
  'Hummingbird hovering near flower',
  'Sea turtle swimming in turquoise water',
];

/**
 * Get a random prompt from the collection
 * @param {string|null} lastPrompt - Previously selected prompt to avoid duplicates
 * @returns {string} Random seed prompt
 */
export function getRandomPrompt(lastPrompt = null) {
  if (seedPrompts.length === 0) {
    return '';
  }

  if (seedPrompts.length === 1) {
    return seedPrompts[0];
  }

  // Filter out last prompt to prevent consecutive duplicates
  const availablePrompts = lastPrompt
    ? seedPrompts.filter(p => p !== lastPrompt)
    : seedPrompts;

  const randomIndex = Math.floor(Math.random() * availablePrompts.length);
  return availablePrompts[randomIndex];
}

export default seedPrompts;
