import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { spawn, execSync, execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEPLOY_CONFIG_PATH = path.join(__dirname, '..', '.deploy-config.json');
const FRONTEND_ENV_PATH = path.join(__dirname, '..', '..', 'frontend', '.env');

export function createInterface() {
  return readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });
}

export function question(rl, query) {
  return new Promise(resolve => rl.question(query, resolve));
}

async function checkPrerequisites() {
  console.log('Checking prerequisites...');
  try {
    execSync('aws sts get-caller-identity', { stdio: 'ignore' });
  } catch (e) {
    console.error('Error: AWS CLI not configured or missing credentials. Run "aws configure".');
    process.exit(1);
  }

  try {
    execSync('sam --version', { stdio: 'ignore' });
  } catch (e) {
    console.error('Error: SAM CLI not installed.');
    process.exit(1);
  }
  console.log('✓ Prerequisites OK\n');
}

/**
 * Validate configuration values
 * @param {object} config - Configuration object to validate
 * @returns {object} - { valid: boolean, errors: string[] }
 */
export function validateConfig(config) {
  const errors = [];

  // Validate Lambda memory (128-10240 MB)
  if (config.lambdaMemory) {
    const memoryNum = parseInt(config.lambdaMemory, 10);
    if (isNaN(memoryNum) || memoryNum < 128 || memoryNum > 10240) {
      errors.push(`Invalid lambdaMemory: ${config.lambdaMemory}. Must be between 128-10240 MB.`);
    }
  }

  // Validate Lambda timeout (1-900 seconds)
  if (config.lambdaTimeout) {
    const timeoutNum = parseInt(config.lambdaTimeout, 10);
    if (isNaN(timeoutNum) || timeoutNum < 1 || timeoutNum > 900) {
      errors.push(`Invalid lambdaTimeout: ${config.lambdaTimeout}. Must be between 1-900 seconds.`);
    }
  }

  // Validate model count (1-20)
  if (config.modelCount) {
    const count = parseInt(config.modelCount, 10);
    if (isNaN(count) || count < 1 || count > 20) {
      errors.push(`Invalid modelCount: ${config.modelCount}. Must be between 1-20.`);
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

// Default model IDs for each provider
const DEFAULT_MODEL_IDS = {
  openai: 'gpt-image-1',
  google_gemini: 'gemini-2.0-flash-preview-image-generation',
  bedrock_nova: 'amazon.nova-canvas-v1:0',
  bedrock_sd: 'stability.sd3-5-large-v1:0',
  bfl: 'flux-pro-1.1',
  recraft: 'recraft-v3',
  stability: 'stable-diffusion-xl-1024-v1-0'
};

const PROMPT_MODEL_IDS = {
  openai: 'gpt-4o',
  google_gemini: 'gemini-2.0-flash'
};

// Helper to mask API keys for display
function maskKey(key) {
  if (!key) return '(not set)';
  return `****${key.slice(-4)}`;
}

export async function loadOrPromptConfig(rl) {
  // Load existing config as defaults
  let saved = {};
  if (fs.existsSync(DEPLOY_CONFIG_PATH)) {
    try {
      saved = JSON.parse(fs.readFileSync(DEPLOY_CONFIG_PATH, 'utf8'));
      console.log('Loading saved configuration as defaults...\n');
    } catch (e) {
      console.warn('Failed to parse .deploy-config.json, using system defaults.\n');
    }
  }

  // System defaults (used if no saved config)
  const systemDefaults = {
    region: 'us-west-2',
    stackName: 'pixel-prompt-dev',
    lambdaMemory: '3008',
    lambdaTimeout: '900',
    globalRateLimit: '1000',
    ipRateLimit: '100',
    s3RetentionDays: '30'
  };

  // Merge saved config with system defaults
  const defaults = { ...systemDefaults, ...saved };
  const config = {};

  // 1. Basic Config - always prompt
  const regionInput = await question(rl, `AWS Region [${defaults.region}]: `);
  config.region = regionInput.trim() || defaults.region;

  const stackInput = await question(rl, `Stack Name [${defaults.stackName}]: `);
  config.stackName = stackInput.trim() || defaults.stackName;

  // 2. Lambda Configuration - use saved/defaults silently
  config.lambdaMemory = defaults.lambdaMemory;
  config.lambdaTimeout = defaults.lambdaTimeout;
  config.globalRateLimit = defaults.globalRateLimit;
  config.ipRateLimit = defaults.ipRateLimit;
  config.s3RetentionDays = defaults.s3RetentionDays;

  // 3. Prompt Enhancement Model - always prompt
  console.log('\n=== Prompt Enhancement Model ===');
  console.log('Enhances short prompts into detailed image generation prompts.');
  console.log('Supported: openai, google_gemini\n');

  const savedPrompt = defaults.promptModel || {};
  const promptProviderDefault = savedPrompt.provider || 'openai';
  const promptProviderInput = await question(rl, `Provider [${promptProviderDefault}]: `);
  const promptProvider = promptProviderInput.trim() || promptProviderDefault;

  const promptIdDefault = savedPrompt.id || PROMPT_MODEL_IDS[promptProvider] || 'gpt-4o';
  const promptIdInput = await question(rl, `Model ID [${promptIdDefault}]: `);
  const promptId = promptIdInput.trim() || promptIdDefault;

  const promptKeyDefault = savedPrompt.apiKey || '';
  const promptKeyPrompt = promptKeyDefault
    ? `API Key [${maskKey(promptKeyDefault)}]: `
    : 'API Key: ';
  const promptKeyInput = await question(rl, promptKeyPrompt);
  const promptApiKey = promptKeyInput.trim() || promptKeyDefault;

  config.promptModel = {
    provider: promptProvider,
    id: promptId,
    apiKey: promptApiKey
  };

  // 4. Image Generation Models - always prompt
  console.log('\n=== Image Generation Models ===');
  console.log('Supported: openai, google_gemini, bedrock_nova, bedrock_sd, bfl, recraft, stability\n');

  const savedModels = defaults.models || [];
  const modelCountDefault = savedModels.length || 1;
  const countInput = await question(rl, `How many models? [${modelCountDefault}]: `);
  const modelCount = parseInt(countInput.trim() || modelCountDefault, 10);

  config.models = [];

  for (let i = 0; i < modelCount; i++) {
    console.log(`\n--- Model ${i + 1} ---`);
    const existing = savedModels[i] || {};

    const providerDefault = existing.provider || '';
    const providerPrompt = providerDefault
      ? `Provider [${providerDefault}]: `
      : 'Provider: ';
    const providerInput = await question(rl, providerPrompt);
    const provider = providerInput.trim() || providerDefault;

    if (!provider) {
      console.error('Provider is required.');
      i--;
      continue;
    }

    const idDefault = existing.id || DEFAULT_MODEL_IDS[provider] || '';
    const idPrompt = idDefault ? `Model ID [${idDefault}]: ` : 'Model ID: ';
    const idInput = await question(rl, idPrompt);
    const id = idInput.trim() || idDefault;

    if (!id) {
      console.error('Model ID is required.');
      i--;
      continue;
    }

    let apiKey = '';
    if (!provider.startsWith('bedrock')) {
      const keyDefault = existing.apiKey || '';
      const keyPrompt = keyDefault
        ? `API Key [${maskKey(keyDefault)}]: `
        : 'API Key: ';
      const keyInput = await question(rl, keyPrompt);
      apiKey = keyInput.trim() || keyDefault;
    } else {
      console.log('  (Bedrock uses IAM role - no API key needed)');
    }

    config.models.push({ provider, id, apiKey });
  }

  config.modelCount = String(config.models.length);

  // Validate before saving
  const validation = validateConfig(config);
  if (!validation.valid) {
    console.error('\nConfiguration validation errors:');
    validation.errors.forEach(err => console.error(`  - ${err}`));
    process.exit(1);
  }

  // Save config
  fs.writeFileSync(DEPLOY_CONFIG_PATH, JSON.stringify(config, null, 2));
  console.log('\n✓ Configuration saved to .deploy-config.json\n');
  return config;
}

export function buildParameterOverrides(config) {
  const overrides = [
    `LambdaMemory=${config.lambdaMemory}`,
    `LambdaTimeout=${config.lambdaTimeout}`,
    `ModelCount=${config.models.length}`,
    `GlobalRateLimit=${config.globalRateLimit}`,
    `IPRateLimit=${config.ipRateLimit}`,
    `S3RetentionDays=${config.s3RetentionDays}`,
    // Prompt enhancement model
    `PromptModelProvider=${config.promptModel.provider}`,
    `PromptModelId=${config.promptModel.id}`
  ];

  if (config.promptModel.apiKey) {
    overrides.push(`PromptModelApiKey=${config.promptModel.apiKey}`);
  }

  // Image generation models
  config.models.forEach((model, index) => {
    const n = index + 1;
    overrides.push(`Model${n}Provider=${model.provider}`);
    overrides.push(`Model${n}Id=${model.id}`);
    if (model.apiKey) {
      overrides.push(`Model${n}ApiKey=${model.apiKey}`);
    }
  });

  return overrides;
}

function ensureDeploymentBucket(stackName, region) {
  const bucketName = `sam-deploy-${stackName}-${region}`;
  console.log(`Checking deployment bucket: ${bucketName}...`);

  try {
    execSync(`aws s3 ls s3://${bucketName} --region ${region}`, { stdio: 'ignore' });
    console.log('✓ Deployment bucket exists\n');
  } catch (e) {
    console.log('Creating deployment bucket...');
    try {
      execSync(`aws s3 mb s3://${bucketName} --region ${region}`, { stdio: 'inherit' });
      console.log('✓ Deployment bucket created\n');
    } catch (createErr) {
      console.error(`Failed to create deployment bucket: ${createErr.message}`);
      process.exit(1);
    }
  }

  return bucketName;
}

async function buildAndDeploy(config) {
  console.log('Building SAM application...');
  try {
    execSync('sam build', { stdio: 'inherit', cwd: path.join(__dirname, '..') });
  } catch (e) {
    console.error('Build failed.');
    process.exit(1);
  }

  // Create deployment bucket if needed
  const deployBucket = ensureDeploymentBucket(config.stackName, config.region);

  console.log('\nDeploying SAM application...');
  console.log('This may take several minutes...\n');

  const paramOverrides = buildParameterOverrides(config);

  return new Promise((resolve, reject) => {
    const args = [
      'deploy',
      '--stack-name', config.stackName,
      '--region', config.region,
      '--s3-bucket', deployBucket,
      '--s3-prefix', config.stackName,
      '--capabilities', 'CAPABILITY_IAM',
      '--no-confirm-changeset',
      '--no-fail-on-empty-changeset',
      '--parameter-overrides', ...paramOverrides
    ];

    const deploy = spawn('sam', args, {
      cwd: path.join(__dirname, '..'),
      shell: true
    });

    let stdoutData = '';

    deploy.stdout.on('data', (data) => {
      const str = data.toString();
      process.stdout.write(str);
      stdoutData += str;
    });

    deploy.stderr.on('data', (data) => {
      process.stderr.write(data);
    });

    deploy.on('close', (code) => {
      if (code !== 0) {
        console.error(`Deployment failed with code ${code}`);
        reject(new Error('Deployment failed'));
      } else {
        resolve(stdoutData);
      }
    });
  });
}

async function getStackOutputs(stackName, region) {
  try {
    const result = execFileSync('aws', [
      'cloudformation',
      'describe-stacks',
      '--stack-name',
      stackName,
      '--region',
      region,
      '--query',
      'Stacks[0].Outputs',
      '--output',
      'json'
    ]);
    return JSON.parse(result.toString());
  } catch (e) {
    console.error('Failed to get stack outputs');
    return [];
  }
}

function updateFrontendEnv(apiUrl, cloudfrontDomain, s3Bucket, environment) {
  const newEnvContent = `# Auto-generated by deploy.js on ${new Date().toISOString()}
# Environment: ${environment}

# Backend API endpoint
VITE_API_ENDPOINT=${apiUrl}

# CloudFront domain for image delivery
VITE_CLOUDFRONT_DOMAIN=${cloudfrontDomain}

# S3 bucket name (for reference)
VITE_S3_BUCKET=${s3Bucket}

# Environment identifier
VITE_ENVIRONMENT=${environment}
`;

  fs.writeFileSync(FRONTEND_ENV_PATH, newEnvContent);
  console.log(`\nUpdated frontend .env with API URL: ${apiUrl}`);
}

async function main() {
  console.log('=== Pixel Prompt Backend Deployment ===\n');

  await checkPrerequisites();
  const rl = createInterface();
  const config = await loadOrPromptConfig(rl);
  rl.close();

  // Display configuration summary
  console.log('=== Configuration Summary ===');
  console.log(`Region:       ${config.region}`);
  console.log(`Stack:        ${config.stackName}`);
  console.log(`\nPrompt Model: ${config.promptModel.provider} / ${config.promptModel.id}`);
  console.log(`\nImage Models: ${config.models.length}`);
  config.models.forEach((m, i) => {
    console.log(`  ${i + 1}: ${m.provider} / ${m.id}`);
  });
  console.log('');

  try {
    await buildAndDeploy(config);
  } catch (e) {
    console.error('Deployment error:', e.message);
    process.exit(1);
  }

  console.log('\nDeployment complete. Fetching outputs...');
  const outputs = await getStackOutputs(config.stackName, config.region);

  const apiUrlOutput = outputs.find(o => o.OutputKey === 'ApiEndpoint');
  const cloudfrontOutput = outputs.find(o => o.OutputKey === 'CloudFrontDomain');
  const s3BucketOutput = outputs.find(o => o.OutputKey === 'S3BucketName');

  if (apiUrlOutput) {
    updateFrontendEnv(
      apiUrlOutput.OutputValue,
      cloudfrontOutput?.OutputValue || '',
      s3BucketOutput?.OutputValue || '',
      config.stackName
    );
  } else {
    console.warn('Could not find ApiEndpoint in stack outputs.');
  }

  // Summary
  console.log('\n=== Deployment Complete ===\n');
  console.log(`Stack Name:        ${config.stackName}`);
  console.log(`API Endpoint:      ${apiUrlOutput?.OutputValue || 'N/A'}`);
  console.log(`CloudFront Domain: ${cloudfrontOutput?.OutputValue || 'N/A'}`);
  console.log(`S3 Bucket:         ${s3BucketOutput?.OutputValue || 'N/A'}`);
  console.log('\nNext steps:');
  console.log('1. Frontend .env has been updated');
  console.log('2. Build frontend: cd frontend && npm run build');
  console.log('3. Preview frontend: cd frontend && npm run preview');
  console.log('4. Deploy frontend to your hosting platform');
  console.log('\nNote: CloudFront distribution may take up to 15 minutes to fully deploy');
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main();
}
