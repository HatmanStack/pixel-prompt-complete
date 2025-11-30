import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { spawn, execSync, execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEPLOY_CONFIG_PATH = path.join(__dirname, '..', '.deploy-config.json');
const SAM_CONFIG_PATH = path.join(__dirname, '..', 'samconfig.toml');
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

  // Validate rate limits
  if (config.globalRateLimit) {
    const limit = parseInt(config.globalRateLimit, 10);
    if (isNaN(limit) || limit < 1) {
      errors.push(`Invalid globalRateLimit: ${config.globalRateLimit}. Must be a positive integer.`);
    }
  }

  if (config.ipRateLimit) {
    const limit = parseInt(config.ipRateLimit, 10);
    if (isNaN(limit) || limit < 1) {
      errors.push(`Invalid ipRateLimit: ${config.ipRateLimit}. Must be a positive integer.`);
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

export async function loadOrPromptConfig(rl) {
  let config = {};
  if (fs.existsSync(DEPLOY_CONFIG_PATH)) {
    try {
      config = JSON.parse(fs.readFileSync(DEPLOY_CONFIG_PATH, 'utf8'));
      console.log('Loaded configuration from .deploy-config.json');

      // Validate loaded config
      const validation = validateConfig(config);
      if (!validation.valid) {
        console.warn('Configuration validation errors:');
        validation.errors.forEach(err => console.warn(`  - ${err}`));
        console.warn('Please fix .deploy-config.json or delete it to re-prompt.');
        process.exit(1);
      }
    } catch (e) {
      console.warn('Failed to parse .deploy-config.json, prompting for new config.');
    }
  }

  // Defaults based on template.yaml
  const defaults = {
    region: 'us-east-1',
    stackName: 'pixel-prompt-dev',
    lambdaMemory: '3008',
    lambdaTimeout: '900',
    modelCount: '1',
    promptModelIndex: '1',
    globalRateLimit: '1000',
    ipRateLimit: '100',
    s3RetentionDays: '30'
  };

  // 1. Basic Config
  if (!config.region) {
    const input = await question(rl, `Enter AWS Region [${defaults.region}]: `);
    config.region = input.trim() || defaults.region;
  }

  if (!config.stackName) {
    const input = await question(rl, `Enter Stack Name [${defaults.stackName}]: `);
    config.stackName = input.trim() || defaults.stackName;
  }

  // 2. Lambda Configuration
  if (!config.lambdaMemory) {
    const input = await question(rl, `Enter Lambda Memory (MB) [${defaults.lambdaMemory}]: `);
    config.lambdaMemory = input.trim() || defaults.lambdaMemory;
  }

  if (!config.lambdaTimeout) {
    const input = await question(rl, `Enter Lambda Timeout (seconds) [${defaults.lambdaTimeout}]: `);
    config.lambdaTimeout = input.trim() || defaults.lambdaTimeout;
  }

  // 3. Model Configuration
  if (!config.modelCount) {
    const input = await question(rl, `Enter Model Count (1-20) [${defaults.modelCount}]: `);
    config.modelCount = input.trim() || defaults.modelCount;
  }

  if (!config.promptModelIndex) {
    const input = await question(rl, `Enter Prompt Model Index (1-${config.modelCount}) [${defaults.promptModelIndex}]: `);
    config.promptModelIndex = input.trim() || defaults.promptModelIndex;
  }

  // 4. Rate Limiting (use defaults, advanced users can edit config file)
  if (!config.globalRateLimit) {
    config.globalRateLimit = defaults.globalRateLimit;
  }
  if (!config.ipRateLimit) {
    config.ipRateLimit = defaults.ipRateLimit;
  }
  if (!config.s3RetentionDays) {
    config.s3RetentionDays = defaults.s3RetentionDays;
  }

  // Save config
  fs.writeFileSync(DEPLOY_CONFIG_PATH, JSON.stringify(config, null, 2));
  console.log('Configuration saved to .deploy-config.json\n');
  return config;
}

export function generateSamConfig(config) {
  // Build SAM parameter overrides from config
  // Note: API keys and model configs are not stored - SAM will prompt if missing
  const overrides = [
    `LambdaMemory=${config.lambdaMemory}`,
    `LambdaTimeout=${config.lambdaTimeout}`,
    `ModelCount=${config.modelCount}`,
    `PromptModelIndex=${config.promptModelIndex}`,
    `GlobalRateLimit=${config.globalRateLimit}`,
    `IPRateLimit=${config.ipRateLimit}`,
    `S3RetentionDays=${config.s3RetentionDays}`
  ];

  const parameterOverrides = overrides.join(' ');

  const content = `version = 0.1
[default.deploy.parameters]
stack_name = "${config.stackName}"
region = "${config.region}"
capabilities = "CAPABILITY_IAM"
parameter_overrides = "${parameterOverrides}"
resolve_s3 = true
`;
  fs.writeFileSync(SAM_CONFIG_PATH, content);
  console.log('Generated samconfig.toml');
  return content;
}

async function buildAndDeploy() {
  console.log('Building SAM application...');
  try {
    execSync('sam build', { stdio: 'inherit', cwd: path.join(__dirname, '..') });
  } catch (e) {
    console.error('Build failed.');
    process.exit(1);
  }

  console.log('\nDeploying SAM application...');
  console.log('This may take several minutes...\n');

  return new Promise((resolve, reject) => {
    const deploy = spawn('sam', ['deploy', '--no-confirm-changeset', '--no-fail-on-empty-changeset'], {
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
  let envContent = '';
  if (fs.existsSync(FRONTEND_ENV_PATH)) {
    envContent = fs.readFileSync(FRONTEND_ENV_PATH, 'utf8');
  }

  // Build new env content
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

  generateSamConfig(config);

  try {
    await buildAndDeploy();
  } catch (e) {
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
