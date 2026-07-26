import fs from 'fs';
import path from 'path';
import { spawn, execSync, execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ENV_DEPLOY_PATH = path.join(__dirname, '..', '.env.deploy');
const FRONTEND_ENV_PATH = path.join(__dirname, '..', '..', 'frontend', '.env');

/**
 * Parse .env.deploy file into config object
 */
function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return null;
  }

  const content = fs.readFileSync(filePath, 'utf8');
  const config = {};

  content.split('\n').forEach(line => {
    if (!line.trim() || line.trim().startsWith('#')) {
      return;
    }

    const eqIndex = line.indexOf('=');
    if (eqIndex === -1) return;

    const key = line.slice(0, eqIndex).trim();
    const value = line.slice(eqIndex + 1).trim();
    config[key] = value;
  });

  return config;
}

/**
 * Convert env vars to structured config for v2 (4 fixed models)
 */
function envToConfig(env) {
  return {
    region: env.AWS_REGION || 'us-west-2',
    stackName: env.STACK_NAME || 'pixel-prompt-v2',
    globalRateLimit: env.GLOBAL_RATE_LIMIT || '1000',
    ipRateLimit: env.IP_RATE_LIMIT || '100',

    // Prompt enhancement model
    promptModel: {
      provider: env.PROMPT_MODEL_PROVIDER || 'openai',
      id: env.PROMPT_MODEL_ID || 'gpt-4o',
      apiKey: env.PROMPT_MODEL_API_KEY || ''
    },

    // 4 Fixed models
    // AUTH_ENABLED has no default in the template, by design: there is no
    // safe value to assume. Deploy fails loudly rather than guessing.
    authEnabled: env.AUTH_ENABLED,
    alarmEmail: env.ALARM_EMAIL || '',
    spend: {
      monthlyCeilingUsdMicros: env.MONTHLY_SPEND_CEILING_USD_MICROS || '',
      dailyCeilingUsdMicros: env.GLOBAL_DAILY_SPEND_CEILING_USD_MICROS || ''
    },
    models: {
      gemini: {
        enabled: (env.GEMINI_ENABLED || 'true').toLowerCase() === 'true',
        apiKey: env.GEMINI_API_KEY || '',
        modelId: env.GEMINI_MODEL_ID || ''
      },
      nova: {
        enabled: (env.NOVA_ENABLED || 'true').toLowerCase() === 'true',
        modelId: env.NOVA_MODEL_ID || ''
      },
      openai: {
        enabled: (env.OPENAI_ENABLED || 'true').toLowerCase() === 'true',
        apiKey: env.OPENAI_API_KEY || '',
        modelId: env.OPENAI_MODEL_ID || ''
      },
      firefly: {
        enabled: (env.FIREFLY_ENABLED || 'true').toLowerCase() === 'true',
        clientId: env.FIREFLY_CLIENT_ID || '',
        clientSecret: env.FIREFLY_CLIENT_SECRET || '',
        modelId: env.FIREFLY_MODEL_ID || ''
      }
    }
  };
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
 */
export function validateConfig(config) {
  const errors = [];

  if (!config.region) {
    errors.push('AWS_REGION is required');
  }

  if (!config.stackName) {
    errors.push('STACK_NAME is required');
  }

  // Check at least one model is enabled
  const enabledModels = Object.entries(config.models)
    .filter(([_, m]) => m.enabled);

  if (enabledModels.length === 0) {
    errors.push('At least one image generation model must be enabled');
  }

  // Credentials differ per provider, so a blanket apiKey check is wrong:
  // Nova authenticates with the Lambda execution role and has no key at all,
  // and Firefly uses OAuth2 client credentials rather than a single key.
  // Checking `model.apiKey` for every model rejected a fresh, unedited
  // .env.deploy.example with a spurious NOVA_API_KEY error.
  enabledModels.forEach(([name, model]) => {
    if (name === 'nova') {
      return; // Lambda execution role, no credentials to supply
    }
    if (name === 'firefly') {
      if (!model.clientId || !model.clientSecret) {
        errors.push('FIREFLY_CLIENT_ID and FIREFLY_CLIENT_SECRET are required when FIREFLY_ENABLED=true');
      }
      return;
    }
    if (!model.apiKey) {
      errors.push(`${name.toUpperCase()}_API_KEY is required when ${name.toUpperCase()}_ENABLED=true`);
    }
  });

  if (config.authEnabled !== 'true' && config.authEnabled !== 'false') {
    errors.push('AUTH_ENABLED must be set explicitly to "true" or "false"');
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

function maskKey(key) {
  if (!key) return '(not set)';
  return `****${key.slice(-4)}`;
}

export function loadConfig() {
  const env = parseEnvFile(ENV_DEPLOY_PATH);

  if (!env) {
    console.error(`Error: ${ENV_DEPLOY_PATH} not found.`);
    console.error('Copy .env.deploy.example to .env.deploy and configure it.');
    process.exit(1);
  }

  console.log('Loading configuration from .env.deploy...\n');
  return envToConfig(env);
}

export function buildParameterOverrides(config) {
  // Every key here must exist in template.yaml. Passing an unknown parameter
  // fails the whole deploy, which is how Flux and Recraft -- models this
  // stack has not had for some time -- were able to sit here unnoticed.
  if (config.authEnabled !== 'true' && config.authEnabled !== 'false') {
    console.error(
      'Error: AUTH_ENABLED must be set to "true" or "false" in .env.deploy.\n' +
      'There is no safe default: "false" serves unauthenticated traffic,\n' +
      '"true" requires Cognito and a guest token secret.'
    );
    process.exit(1);
  }

  const overrides = [
    `AuthEnabled=${config.authEnabled}`,

    // Prompt model
    `PromptModelProvider=${config.promptModel.provider}`,
    `PromptModelId=${config.promptModel.id}`,

    // The four fixed models
    `GeminiEnabled=${config.models.gemini.enabled}`,
    `NovaEnabled=${config.models.nova.enabled}`,
    `OpenaiEnabled=${config.models.openai.enabled}`,
    `FireflyEnabled=${config.models.firefly.enabled}`
  ];

  // Model ids only when overridden, so the template defaults stay
  // authoritative rather than being shadowed by empty strings.
  const modelIds = {
    GeminiModelId: config.models.gemini.modelId,
    NovaModelId: config.models.nova.modelId,
    OpenaiModelId: config.models.openai.modelId,
    FireflyModelId: config.models.firefly.modelId
  };
  for (const [key, value] of Object.entries(modelIds)) {
    if (value) overrides.push(`${key}=${value}`);
  }

  // Credentials only if set. Nova uses the Lambda execution role.
  const secrets = {
    PromptModelApiKey: config.promptModel.apiKey,
    GeminiApiKey: config.models.gemini.apiKey,
    OpenaiApiKey: config.models.openai.apiKey,
    FireflyClientId: config.models.firefly.clientId,
    FireflyClientSecret: config.models.firefly.clientSecret
  };
  for (const [key, value] of Object.entries(secrets)) {
    if (value) overrides.push(`${key}=${value}`);
  }

  // Operational settings. Without AlarmEmail the alarms still fire and are
  // visible in CloudWatch, but nothing is delivered.
  if (config.alarmEmail) overrides.push(`AlarmEmail=${config.alarmEmail}`);
  if (config.spend.monthlyCeilingUsdMicros) {
    overrides.push(`MonthlySpendCeilingUsdMicros=${config.spend.monthlyCeilingUsdMicros}`);
  }
  if (config.spend.dailyCeilingUsdMicros) {
    overrides.push(`GlobalDailySpendCeilingUsdMicros=${config.spend.dailyCeilingUsdMicros}`);
  }

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
  console.log('=== Pixel Prompt v2 Deployment ===\n');

  await checkPrerequisites();
  const config = loadConfig();

  // Validate
  const validation = validateConfig(config);
  if (!validation.valid) {
    console.error('Configuration errors:');
    validation.errors.forEach(err => console.error(`  - ${err}`));
    process.exit(1);
  }

  // Count enabled models
  const enabledModels = Object.entries(config.models)
    .filter(([_, m]) => m.enabled)
    .map(([name, _]) => name);

  // Display configuration summary
  console.log('=== Configuration Summary ===');
  console.log(`Region:       ${config.region}`);
  console.log(`Stack:        ${config.stackName}`);
  console.log(`\nPrompt Model: ${config.promptModel.provider} / ${config.promptModel.id} [${maskKey(config.promptModel.apiKey)}]`);
  console.log(`\nImage Models: ${enabledModels.length} enabled`);

  Object.entries(config.models).forEach(([name, model]) => {
    const status = model.enabled ? '✓' : '✗';
    const keyInfo = model.enabled ? `[${maskKey(model.apiKey)}]` : '';
    console.log(`  ${status} ${name.padEnd(8)} ${model.modelId} ${keyInfo}`);
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
