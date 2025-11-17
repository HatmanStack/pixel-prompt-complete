#!/usr/bin/env bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Lighthouse Frontend Audit ===${NC}"
echo ""

# Check if Lighthouse is installed
if ! command -v lighthouse &> /dev/null; then
    echo -e "${RED}Error: Lighthouse CLI not found${NC}"
    echo "Install with: npm install -g lighthouse"
    echo "Or use npx: npx lighthouse <url>"
    exit 1
fi

# Check if we're in the right directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}Error: Frontend directory not found${NC}"
    exit 1
fi

cd "$FRONTEND_DIR"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}node_modules not found, installing dependencies...${NC}"
    npm install
fi

echo -e "${YELLOW}Building frontend...${NC}"
if ! npm run build; then
    echo -e "${RED}Error: Build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Build successful${NC}"
echo ""

# Measure bundle size
echo -e "${YELLOW}Measuring bundle size...${NC}"
DIST_SIZE=$(du -sh dist/ | cut -f1)
echo "  Total dist/ size: $DIST_SIZE"

# Find JavaScript bundles
if [ -d "dist/assets" ]; then
    JS_FILES=$(find dist/assets -name "*.js" -type f)
    for file in $JS_FILES; do
        SIZE=$(du -h "$file" | cut -f1)
        FILENAME=$(basename "$file")
        echo "  $FILENAME: $SIZE"

        # Create gzipped version to measure compressed size
        if command -v gzip &> /dev/null; then
            GZIP_FILE="${file}.gz"
            gzip -c "$file" > "$GZIP_FILE"
            GZIP_SIZE=$(du -h "$GZIP_FILE" | cut -f1)
            echo "    (gzipped: $GZIP_SIZE)"
            rm "$GZIP_FILE"
        fi
    done
fi

echo ""

# Start preview server in background
echo -e "${YELLOW}Starting preview server...${NC}"
npm run preview &
SERVER_PID=$!

# Wait for server to start
echo "Waiting for server to start..."
sleep 5

# Check if server is running
if ! curl -s http://localhost:4173 > /dev/null; then
    echo -e "${RED}Error: Preview server not responding${NC}"
    kill $SERVER_PID 2>/dev/null || true
    exit 1
fi

echo -e "${GREEN}✓ Preview server running on http://localhost:4173${NC}"
echo ""

# Create results directory
RESULTS_DIR="$SCRIPT_DIR/../lighthouse-results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_PREFIX="lighthouse-$TIMESTAMP"

echo -e "${YELLOW}Running Lighthouse audit...${NC}"
echo "This may take 1-2 minutes..."
echo ""

# Run Lighthouse
lighthouse http://localhost:4173 \
    --output html \
    --output json \
    --output-path "$RESULTS_DIR/$REPORT_PREFIX" \
    --chrome-flags="--headless --no-sandbox" \
    --quiet \
    2>&1 | grep -v "WARNING"

# Kill preview server
kill $SERVER_PID 2>/dev/null || true

echo ""
echo -e "${GREEN}✓ Lighthouse audit complete${NC}"
echo ""

# Parse JSON results
JSON_FILE="$RESULTS_DIR/${REPORT_PREFIX}.report.json"
HTML_FILE="$RESULTS_DIR/${REPORT_PREFIX}.report.html"

if [ -f "$JSON_FILE" ]; then
    echo -e "${YELLOW}=== Lighthouse Scores ===${NC}"
    echo ""

    # Extract scores using grep and sed (works without jq)
    PERFORMANCE=$(grep -o '"performance":[0-9.]*' "$JSON_FILE" | head -1 | cut -d':' -f2)
    ACCESSIBILITY=$(grep -o '"accessibility":[0-9.]*' "$JSON_FILE" | head -1 | cut -d':' -f2)
    BEST_PRACTICES=$(grep -o '"best-practices":[0-9.]*' "$JSON_FILE" | head -1 | cut -d':' -f2)
    SEO=$(grep -o '"seo":[0-9.]*' "$JSON_FILE" | head -1 | cut -d':' -f2)

    # Convert to 0-100 scale
    PERFORMANCE_SCORE=$(echo "$PERFORMANCE * 100" | bc | cut -d'.' -f1)
    ACCESSIBILITY_SCORE=$(echo "$ACCESSIBILITY * 100" | bc | cut -d'.' -f1)
    BEST_PRACTICES_SCORE=$(echo "$BEST_PRACTICES * 100" | bc | cut -d'.' -f1)
    SEO_SCORE=$(echo "$SEO * 100" | bc | cut -d'.' -f1)

    # Color code based on score
    score_color() {
        local score=$1
        if [ "$score" -ge 90 ]; then
            echo -e "${GREEN}$score${NC}"
        elif [ "$score" -ge 50 ]; then
            echo -e "${YELLOW}$score${NC}"
        else
            echo -e "${RED}$score${NC}"
        fi
    }

    echo "  Performance:    $(score_color $PERFORMANCE_SCORE) / 100  (target: > 90)"
    echo "  Accessibility:  $(score_color $ACCESSIBILITY_SCORE) / 100  (target: > 90)"
    echo "  Best Practices: $(score_color $BEST_PRACTICES_SCORE) / 100  (target: > 90)"
    echo "  SEO:            $(score_color $SEO_SCORE) / 100  (target: > 90)"
    echo ""

    # Extract Core Web Vitals
    echo -e "${YELLOW}=== Core Web Vitals ===${NC}"
    echo ""

    # Extract LCP (Largest Contentful Paint)
    LCP=$(grep -o '"largest-contentful-paint"[^}]*"numericValue":[0-9.]*' "$JSON_FILE" | grep -o '[0-9.]*$' | head -1)
    if [ -n "$LCP" ]; then
        LCP_SEC=$(echo "scale=2; $LCP / 1000" | bc)
        if (( $(echo "$LCP_SEC < 2.5" | bc -l) )); then
            echo -e "  LCP (Largest Contentful Paint): ${GREEN}${LCP_SEC}s${NC} (target: < 2.5s)"
        else
            echo -e "  LCP (Largest Contentful Paint): ${YELLOW}${LCP_SEC}s${NC} (target: < 2.5s)"
        fi
    fi

    # Extract CLS (Cumulative Layout Shift)
    CLS=$(grep -o '"cumulative-layout-shift"[^}]*"numericValue":[0-9.]*' "$JSON_FILE" | grep -o '[0-9.]*$' | head -1)
    if [ -n "$CLS" ]; then
        if (( $(echo "$CLS < 0.1" | bc -l) )); then
            echo -e "  CLS (Cumulative Layout Shift):  ${GREEN}${CLS}${NC} (target: < 0.1)"
        else
            echo -e "  CLS (Cumulative Layout Shift):  ${YELLOW}${CLS}${NC} (target: < 0.1)"
        fi
    fi

    # Extract TBT (Total Blocking Time)
    TBT=$(grep -o '"total-blocking-time"[^}]*"numericValue":[0-9.]*' "$JSON_FILE" | grep -o '[0-9.]*$' | head -1)
    if [ -n "$TBT" ]; then
        if (( $(echo "$TBT < 200" | bc -l) )); then
            echo -e "  TBT (Total Blocking Time):       ${GREEN}${TBT}ms${NC} (target: < 200ms)"
        else
            echo -e "  TBT (Total Blocking Time):       ${YELLOW}${TBT}ms${NC} (target: < 200ms)"
        fi
    fi

    # Extract FCP (First Contentful Paint)
    FCP=$(grep -o '"first-contentful-paint"[^}]*"numericValue":[0-9.]*' "$JSON_FILE" | grep -o '[0-9.]*$' | head -1)
    if [ -n "$FCP" ]; then
        FCP_SEC=$(echo "scale=2; $FCP / 1000" | bc)
        if (( $(echo "$FCP_SEC < 1.8" | bc -l) )); then
            echo -e "  FCP (First Contentful Paint):    ${GREEN}${FCP_SEC}s${NC} (target: < 1.8s)"
        else
            echo -e "  FCP (First Contentful Paint):    ${YELLOW}${FCP_SEC}s${NC} (target: < 1.8s)"
        fi
    fi

    echo ""

    # Check if all targets met
    ALL_PASS=true
    if [ "$PERFORMANCE_SCORE" -lt 90 ]; then ALL_PASS=false; fi
    if [ "$ACCESSIBILITY_SCORE" -lt 90 ]; then ALL_PASS=false; fi
    if [ "$BEST_PRACTICES_SCORE" -lt 90 ]; then ALL_PASS=false; fi
    if [ "$SEO_SCORE" -lt 90 ]; then ALL_PASS=false; fi

    if [ "$ALL_PASS" = true ]; then
        echo -e "${GREEN}✓ All Lighthouse targets met!${NC}"
    else
        echo -e "${YELLOW}⚠ Some Lighthouse targets not met${NC}"
        echo "  Review the full report for optimization opportunities"
    fi
fi

echo ""
echo -e "${YELLOW}Results saved to:${NC}"
echo "  HTML Report: $HTML_FILE"
echo "  JSON Report: $JSON_FILE"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Open HTML report: open $HTML_FILE"
echo "2. Review Lighthouse opportunities and diagnostics"
echo "3. Update docs/PERFORMANCE.md with results"
echo "4. Address any failing scores (< 90)"
echo ""
