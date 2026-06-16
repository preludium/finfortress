#!/usr/bin/env bash
# Create GitHub labels for the AI workflow.
# Usage: bash scripts/setup_labels.sh
# Requires: gh CLI authenticated (gh auth login)

set -euo pipefail

REPO="${1:-}"
REPO_FLAG=""
if [ -n "$REPO" ]; then
  REPO_FLAG="--repo $REPO"
fi

create_label() {
  local name="$1" color="$2" description="$3"
  if gh label list $REPO_FLAG --json name --jq '.[].name' | grep -qx "$name"; then
    echo "  exists: $name — skipping"
  else
    gh label create "$name" --color "$color" --description "$description" $REPO_FLAG
    echo "  created: $name"
  fi
}

echo "Setting up AI workflow labels..."
create_label "ai-implement" "0075ca" "Trigger for AI workflow"
create_label "ai-generated" "e4e669" "PR created by AI"
create_label "ai-failed"    "d73a4a" "AI could not implement"
echo "Done."
