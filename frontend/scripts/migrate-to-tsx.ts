#!/usr/bin/env npx ts-node

/**
 * Migration Helper Script
 * Assists with JSX to TSX file conversion
 *
 * Usage:
 *   npx ts-node scripts/migrate-to-tsx.ts --dry-run  # Preview changes
 *   npx ts-node scripts/migrate-to-tsx.ts            # Execute migration
 */

import * as fs from 'fs';
import * as path from 'path';

const SRC_DIR = path.join(__dirname, '..', 'src');
const DRY_RUN = process.argv.includes('--dry-run');

interface MigrationResult {
  file: string;
  oldPath: string;
  newPath: string;
  status: 'pending' | 'renamed' | 'skipped' | 'error';
  error?: string;
}

function findJsxFiles(dir: string): string[] {
  const files: string[] = [];

  function walk(currentDir: string) {
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(currentDir, entry.name);

      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.name.endsWith('.jsx')) {
        files.push(fullPath);
      }
    }
  }

  walk(dir);
  return files;
}

function migrateFile(filePath: string): MigrationResult {
  const newPath = filePath.replace(/\.jsx$/, '.tsx');
  const relativePath = path.relative(SRC_DIR, filePath);

  const result: MigrationResult = {
    file: relativePath,
    oldPath: filePath,
    newPath: newPath,
    status: 'pending',
  };

  if (fs.existsSync(newPath)) {
    result.status = 'skipped';
    result.error = 'TSX file already exists';
    return result;
  }

  if (DRY_RUN) {
    result.status = 'pending';
    return result;
  }

  try {
    fs.renameSync(filePath, newPath);
    result.status = 'renamed';
  } catch (err) {
    result.status = 'error';
    result.error = err instanceof Error ? err.message : String(err);
  }

  return result;
}

function main() {
  console.log('\n🔄 JSX to TSX Migration Helper\n');
  console.log(`Mode: ${DRY_RUN ? 'DRY RUN (no changes)' : 'EXECUTE'}`);
  console.log(`Source: ${SRC_DIR}\n`);

  const jsxFiles = findJsxFiles(SRC_DIR);

  if (jsxFiles.length === 0) {
    console.log('✅ No JSX files found. Migration complete!\n');
    return;
  }

  console.log(`Found ${jsxFiles.length} JSX files:\n`);

  const results = jsxFiles.map(migrateFile);

  // Print results
  for (const result of results) {
    const icon =
      result.status === 'renamed' ? '✅' :
      result.status === 'pending' ? '📝' :
      result.status === 'skipped' ? '⏭️' : '❌';

    console.log(`${icon} ${result.file}`);
    if (result.error) {
      console.log(`   └─ ${result.error}`);
    }
  }

  // Summary
  const renamed = results.filter(r => r.status === 'renamed').length;
  const pending = results.filter(r => r.status === 'pending').length;
  const skipped = results.filter(r => r.status === 'skipped').length;
  const errors = results.filter(r => r.status === 'error').length;

  console.log('\n--- Summary ---');
  if (DRY_RUN) {
    console.log(`📝 Would rename: ${pending} files`);
  } else {
    console.log(`✅ Renamed: ${renamed} files`);
  }
  if (skipped > 0) console.log(`⏭️ Skipped: ${skipped} files`);
  if (errors > 0) console.log(`❌ Errors: ${errors} files`);

  console.log('\n⚠️  Note: After migration, you need to:');
  console.log('   1. Add type annotations to components');
  console.log('   2. Update imports if needed');
  console.log('   3. Run `npm run typecheck` to find type errors\n');
}

main();
