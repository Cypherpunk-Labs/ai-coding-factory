#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Validating Corporate R&D Policy artifacts..."

require_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "ERROR: Missing required file: $file"
    exit 1
  fi
  echo "OK: $file"
}

require_file "$ROOT/CORPORATE_RND_POLICY.md"
require_file "$ROOT/docs/governance/GOVERNANCE.md"
require_file "$ROOT/docs/traceability/TRACEABILITY.md"
require_file "$ROOT/docs/testing/TESTING-STRATEGY.md"
require_file "$ROOT/docs/documentation/DOCUMENTATION-REQUIREMENTS.md"

require_file "$ROOT/.opencode/templates/agile/definition-of-done.md"
require_file "$ROOT/.opencode/templates/agile/definition-of-ready.md"
require_file "$ROOT/.opencode/templates/artifacts/ADR-template.md"
require_file "$ROOT/.opencode/templates/artifacts/security-review-checklist.md"
require_file "$ROOT/.opencode/templates/artifacts/threat-model-checklist.md"
require_file "$ROOT/.opencode/templates/artifacts/release-readiness-checklist.md"

require_file "$ROOT/scripts/traceability/traceability.py"
require_file "$ROOT/scripts/coverage/check-coverage.py"

require_file "$ROOT/artifacts/traceability/traceability-report.md"
require_file "$ROOT/artifacts/traceability/release-notes.md"
echo "Corporate R&D Policy artifact validation passed"
