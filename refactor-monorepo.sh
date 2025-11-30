#!/bin/bash
set -euo pipefail

# =============================================================================
# MONOREPO REFACTOR SCRIPT
# Restructures project to: frontend/, backend/, docs/, tests/, root
# =============================================================================

PROJECT_ROOT="/home/christophergalliart/war/pixel-prompt-complete"
cd "$PROJECT_ROOT"

echo "=== MONOREPO REFACTOR SCRIPT ==="
echo "Working directory: $PROJECT_ROOT"
echo ""

# Track deleted files
DELETED_FILES=()
MOVED_FILES=()

# =============================================================================
# PHASE 1: CREATE DOCS DIRECTORY & CONSOLIDATE DOCUMENTATION
# =============================================================================
echo "=== PHASE 1: Consolidating Documentation ==="

mkdir -p docs

# Move root-level docs
for doc in README.md DEBUGGING_ENHANCE.md DEPLOYMENT_WORKFLOW.md; do
    if [ -f "$doc" ]; then
        mv "$doc" docs/
        MOVED_FILES+=("$doc -> docs/$doc")
        echo "  Moved: $doc -> docs/"
    fi
done

# Move backend docs
for doc in backend/DEPLOYMENT.md backend/README.md backend/SECRETS_MANAGER_GUIDE.md backend/TESTING.md backend/tests/README.md; do
    if [ -f "$doc" ]; then
        basename=$(basename "$doc")
        target="docs/backend-${basename}"
        mv "$doc" "$target"
        MOVED_FILES+=("$doc -> $target")
        echo "  Moved: $doc -> $target"
    fi
done

# Move frontend docs
for doc in frontend/API_INTEGRATION.md frontend/DEPLOYMENT.md frontend/README.md frontend/TESTING.md; do
    if [ -f "$doc" ]; then
        basename=$(basename "$doc")
        target="docs/frontend-${basename}"
        mv "$doc" "$target"
        MOVED_FILES+=("$doc -> $target")
        echo "  Moved: $doc -> $target"
    fi
done

# Move .github docs (keep templates in place)
for doc in .github/CONTRIBUTING.md .github/DEPLOYMENT_SECRETS.md .github/PRODUCTION_DEPLOYMENT.md .github/WORKFLOWS.md; do
    if [ -f "$doc" ]; then
        basename=$(basename "$doc")
        target="docs/github-${basename}"
        mv "$doc" "$target"
        MOVED_FILES+=("$doc -> $target")
        echo "  Moved: $doc -> $target"
    fi
done

# Move script docs
if [ -f "scripts/loadtest/README.md" ]; then
    mv scripts/loadtest/README.md docs/loadtest-README.md
    MOVED_FILES+=("scripts/loadtest/README.md -> docs/loadtest-README.md")
    echo "  Moved: scripts/loadtest/README.md -> docs/"
fi

# Delete sound README (noise)
if [ -f "frontend/public/sounds/README.md" ]; then
    rm frontend/public/sounds/README.md
    DELETED_FILES+=("frontend/public/sounds/README.md")
    echo "  Deleted: frontend/public/sounds/README.md"
fi

echo ""

# =============================================================================
# PHASE 2: CENTRALIZE TESTS
# =============================================================================
echo "=== PHASE 2: Centralizing Tests ==="

mkdir -p tests/backend tests/frontend

# Move backend tests
if [ -d "backend/tests/unit" ]; then
    mv backend/tests/unit tests/backend/
    MOVED_FILES+=("backend/tests/unit -> tests/backend/unit")
    echo "  Moved: backend/tests/unit -> tests/backend/"
fi

if [ -d "backend/tests/integration" ]; then
    mv backend/tests/integration tests/backend/
    MOVED_FILES+=("backend/tests/integration -> tests/backend/integration")
    echo "  Moved: backend/tests/integration -> tests/backend/"
fi

if [ -f "backend/tests/requirements.txt" ]; then
    mv backend/tests/requirements.txt tests/backend/
    MOVED_FILES+=("backend/tests/requirements.txt -> tests/backend/")
    echo "  Moved: backend/tests/requirements.txt -> tests/backend/"
fi

# Remove empty backend/tests directory
rmdir backend/tests 2>/dev/null || true

# Move frontend tests
if [ -d "frontend/src/__tests__" ]; then
    mv frontend/src/__tests__ tests/frontend/
    MOVED_FILES+=("frontend/src/__tests__ -> tests/frontend/")
    echo "  Moved: frontend/src/__tests__ -> tests/frontend/"
fi

if [ -f "frontend/src/setupTests.js" ]; then
    mv frontend/src/setupTests.js tests/frontend/
    MOVED_FILES+=("frontend/src/setupTests.js -> tests/frontend/")
    echo "  Moved: frontend/src/setupTests.js -> tests/frontend/"
fi

echo ""

# =============================================================================
# PHASE 3: STRIP DEBUG STATEMENTS
# =============================================================================
echo "=== PHASE 3: Stripping Debug Statements ==="

# Backend: Replace print() with pass or remove entirely
echo "  Processing backend Python files..."

# Remove standalone print statements from backend
find backend/src -name "*.py" -exec sed -i \
    -e '/^[[:space:]]*print(f\?".*")/d' \
    -e 's/print(f\?"[^"]*")/pass  # logging stripped/g' \
    {} \;

# Frontend: Remove console.log statements
echo "  Processing frontend JavaScript files..."

find frontend/src -name "*.js" -o -name "*.jsx" | while read -r file; do
    # Remove console.log lines
    sed -i '/console\.log(/d' "$file" 2>/dev/null || true
    # Remove debugger statements
    sed -i '/^[[:space:]]*debugger;/d' "$file" 2>/dev/null || true
done

echo "  Debug statements stripped"
echo ""

# =============================================================================
# PHASE 4: UPDATE IMPORT PATHS (Frontend tests moved)
# =============================================================================
echo "=== PHASE 4: Updating Import Paths ==="

# Update frontend test imports (now in tests/frontend/)
if [ -d "tests/frontend" ]; then
    find tests/frontend -name "*.test.jsx" -o -name "*.test.js" | while read -r file; do
        # Update imports from '../components' to '../../frontend/src/components'
        sed -i "s|from '\.\./|from '../../frontend/src/|g" "$file" 2>/dev/null || true
        sed -i "s|from \"\.\./|from \"../../frontend/src/|g" "$file" 2>/dev/null || true
        # Update imports from '../../' to '../../../frontend/src/'
        sed -i "s|from '\.\./\.\./|from '../../../frontend/src/|g" "$file" 2>/dev/null || true
        sed -i "s|from \"\.\./\.\./|from \"../../../frontend/src/|g" "$file" 2>/dev/null || true
    done
    echo "  Updated frontend test imports"
fi

# Update setupTests.js path in tests/frontend
if [ -f "tests/frontend/setupTests.js" ]; then
    # Update any relative paths in setupTests
    sed -i "s|from '\.\./|from '../../frontend/src/|g" tests/frontend/setupTests.js 2>/dev/null || true
fi

echo ""

# =============================================================================
# PHASE 5: UPDATE VITE CONFIG FOR NEW TEST LOCATION
# =============================================================================
echo "=== PHASE 5: Updating Build Configs ==="

# Update vite.config.js to point to new test location
if [ -f "frontend/vite.config.js" ]; then
    sed -i "s|setupFiles: '\./src/setupTests\.js'|setupFiles: '../tests/frontend/setupTests.js'|g" frontend/vite.config.js
    sed -i "s|include: \['src/\*\*/\*\.test\.\{js,jsx\}'\]|include: ['../tests/frontend/**/*.test.{js,jsx}']|g" frontend/vite.config.js
    echo "  Updated vite.config.js test paths"
fi

echo ""

# =============================================================================
# PHASE 6: CLEANUP DEAD FILES
# =============================================================================
echo "=== PHASE 6: Cleaning Up Dead Files ==="

# Remove parameters.example.json (secrets should be in SSM/env)
if [ -f "backend/parameters.example.json" ]; then
    rm backend/parameters.example.json
    DELETED_FILES+=("backend/parameters.example.json")
    echo "  Deleted: backend/parameters.example.json"
fi

# Remove duplicate/stale workflow files
if [ -f ".github/workflows/deploy-staging.yml" ]; then
    rm .github/workflows/deploy-staging.yml
    DELETED_FILES+=("deploy-staging.yml")
    echo "  Deleted: .github/workflows/deploy-staging.yml"
fi

if [ -f ".github/workflows/deploy-production.yml" ]; then
    rm .github/workflows/deploy-production.yml
    DELETED_FILES+=("deploy-production.yml")
    echo "  Deleted: .github/workflows/deploy-production.yml"
fi

if [ -f ".github/workflows/test.yml" ]; then
    rm .github/workflows/test.yml
    DELETED_FILES+=("test.yml (replaced by ci.yml)")
    echo "  Deleted: .github/workflows/test.yml"
fi

echo ""

# =============================================================================
# PHASE 7: OUTPUT SUMMARY
# =============================================================================
echo "=== REFACTOR COMPLETE ==="
echo ""
echo "DELETED FILES:"
for f in "${DELETED_FILES[@]}"; do
    echo "  - $f"
done
echo ""
echo "MOVED FILES:"
for f in "${MOVED_FILES[@]}"; do
    echo "  - $f"
done
echo ""
echo "=== FINAL STRUCTURE ==="
tree -a -I '.git|node_modules|__pycache__|.aws-sam|dist|.pytest_cache|htmlcov|.coverage|*.pyc' --dirsfirst -L 3

