#!/bin/bash
# run-autonomous.sh - Safe wrapper for autonomous mode
#
# Usage: ./run-autonomous.sh <project-dir> <task> <task-name>
# Example: ./run-autonomous.sh ~/myproject 'Add login feature' login-feature

set -e

PROJECT_DIR="${1:-.}"
TASK="$2"
TASK_NAME="$3"

# Show usage if insufficient arguments
if [ -z "$TASK" ] || [ -z "$TASK_NAME" ]; then
    echo "SelfAssembler - Autonomous Mode Runner"
    echo ""
    echo "Usage: ./run-autonomous.sh <project-dir> <task> <task-name>"
    echo ""
    echo "Arguments:"
    echo "  project-dir  Path to the project directory"
    echo "  task         Task description (in quotes)"
    echo "  task-name    Short name for the task (used in branch names)"
    echo ""
    echo "Example:"
    echo "  ./run-autonomous.sh ~/myproject 'Add user authentication' auth-feature"
    echo ""
    echo "Environment variables:"
    echo "  ANTHROPIC_API_KEY  Required: Your Anthropic API key"
    echo "  GH_TOKEN           Optional: GitHub token for PR creation"
    echo ""
    exit 1
fi

# Resolve to absolute path
PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY environment variable is not set"
    echo ""
    echo "Set it with:"
    echo "  export ANTHROPIC_API_KEY='your-api-key'"
    exit 1
fi

# Check for GitHub token (warning only)
if [ -z "$GH_TOKEN" ] && [ -z "$GITHUB_TOKEN" ]; then
    echo "Warning: GH_TOKEN not set - PR creation will fail"
    echo "Set it with: export GH_TOKEN='your-github-token'"
    echo ""
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    echo "Install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if image exists, build if not
if ! docker image inspect selfassembler:latest &> /dev/null; then
    echo "Building selfassembler Docker image..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    docker build -t selfassembler:latest "$SCRIPT_DIR"
    echo ""
fi

echo "=== SelfAssembler Autonomous Mode ==="
echo "Project: $PROJECT_DIR"
echo "Task: $TASK"
echo "Name: $TASK_NAME"
echo ""
echo "Container restrictions:"
echo "  - Only /workspace is writable (your project)"
echo "  - No access to host system files"
echo "  - No access to other projects"
echo "  - Network limited to GitHub and Anthropic API"
echo ""

# Run the container
docker run --rm -it \
    --name "selfassembler-${TASK_NAME}" \
    \
    `# Mount project directory as /workspace (read-write)` \
    -v "${PROJECT_DIR}:/workspace" \
    \
    `# Mount git config (read-only) if it exists` \
    ${HOME}/.gitconfig:+-v "${HOME}/.gitconfig:/home/claude/.gitconfig:ro"} \
    \
    `# Mount SSH keys for git push (read-only) if they exist` \
    ${HOME}/.ssh:+-v "${HOME}/.ssh:/home/claude/.ssh:ro"} \
    \
    `# Pass API keys as environment variables` \
    -e "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}" \
    -e "GH_TOKEN=${GH_TOKEN:-$GITHUB_TOKEN}" \
    \
    `# Resource limits` \
    --memory="4g" \
    --cpus="2" \
    \
    `# Security: no privileged access` \
    --security-opt="no-new-privileges:true" \
    --cap-drop=ALL \
    \
    selfassembler:latest \
    "$TASK" \
    --name "$TASK_NAME" \
    --autonomous \
    --no-approvals

EXIT_CODE=$?

echo ""
echo "=== Workflow Complete (exit code: $EXIT_CODE) ==="

exit $EXIT_CODE
