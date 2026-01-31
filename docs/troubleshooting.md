# Troubleshooting Guide

Common issues and their solutions when using SelfAssembler.

## Preflight Failures

### Claude CLI not installed

**Error**: `Claude CLI not installed. Run: npm install -g @anthropic-ai/claude-code`

**Solution**:
```bash
npm install -g @anthropic-ai/claude-code
```

If npm is not available, install Node.js first from https://nodejs.org/

### GitHub CLI not authenticated

**Error**: `GitHub CLI not authenticated. Run: gh auth login`

**Solution**:
```bash
gh auth login
```

Follow the prompts to authenticate with GitHub.

### Git working directory not clean

**Error**: `Git working directory not clean: M file.txt`

**Solution**: Commit, stash, or discard your changes:
```bash
# Option 1: Commit changes
git add . && git commit -m "WIP"

# Option 2: Stash changes
git stash

# Option 3: Discard changes (careful!)
git checkout -- .
```

### Local branch behind remote

**Error**: `Local branch is 5 commits behind origin/main. Run: git pull`

**Solution**:
```bash
git pull origin main
```

## Budget Issues

### Budget exceeded

**Error**: `Budget exceeded: $15.50 >= $15.00`

**Solutions**:

1. **Resume with higher budget**:
   ```bash
   selfassembler --resume checkpoint_xxx --budget 25.0
   ```

2. **Skip expensive phases**:
   ```bash
   selfassembler --resume checkpoint_xxx --skip-to commit_prep
   ```

3. **Increase default budget** in `selfassembler.yaml`:
   ```yaml
   budget_limit_usd: 25.0
   ```

### Insufficient budget for phase

**Error**: `Insufficient budget for implementation. Remaining: $2.00, Estimated: $3.00`

**Solution**: Increase budget or adjust estimated costs:
```yaml
phases:
  implementation:
    estimated_cost: 2.0  # Lower estimate
```

## Approval Timeouts

### Approval timeout

**Error**: `Approval timeout for phase 'planning' after 24.0 hours`

**Solutions**:

1. **Grant approval and resume**:
   ```bash
   selfassembler --approve planning --plans-dir ./plans
   selfassembler --resume checkpoint_xxx
   ```

2. **Increase timeout**:
   ```yaml
   approvals:
     timeout_hours: 72.0
   ```

3. **Disable approvals**:
   ```bash
   selfassembler "Task" --no-approvals
   ```

## Git Issues

### Worktree already exists

**Error**: `Worktree already exists: /path/to/worktree`

**Solution**: Remove the existing worktree:
```bash
git worktree remove --force /path/to/worktree
```

Or clean up all worktrees:
```bash
git worktree prune
```

### Merge conflicts

**Error**: `Merge conflicts could not be auto-resolved: file.txt`

**Solution**:

1. Go to the worktree directory
2. Resolve conflicts manually
3. Resume the workflow:
   ```bash
   selfassembler --resume checkpoint_xxx --skip-to pr_creation
   ```

### Branch push failed

**Error**: Various git push errors

**Solutions**:

- **Authentication**: Ensure SSH keys or tokens are set up
- **Protected branch**: Check branch protection rules
- **Force push needed**: Manually push with `--force-with-lease`

## Claude CLI Issues

### Timeout

**Error**: `Timeout after 600s`

**Solutions**:

1. **Increase timeout**:
   ```yaml
   phases:
     implementation:
       timeout: 7200  # 2 hours
   ```

2. **Reduce task complexity**: Break into smaller tasks

3. **Reduce max turns**:
   ```yaml
   phases:
     implementation:
       max_turns: 50
   ```

### Claude CLI not responding

**Symptoms**: Command hangs, no output

**Solutions**:

1. Check API key: `echo $ANTHROPIC_API_KEY`
2. Check network connectivity
3. Check Claude CLI version: `claude --version`
4. Try running Claude directly: `claude -p "hello"`

## Autonomous Mode Issues

### Container required error

**Error**: `ERROR: Autonomous mode requires container isolation`

**Solution**: Run in Docker:
```bash
./run-autonomous.sh /path/to/project "Task" task-name
```

Or bypass (not recommended):
```bash
export SELFASSEMBLER_ALLOW_HOST_AUTONOMOUS="I_ACCEPT_THE_RISK"
```

### Docker build fails

**Error**: Various Docker build errors

**Solutions**:

1. Ensure Docker is running
2. Check Dockerfile syntax
3. Try building with no cache:
   ```bash
   docker build --no-cache -t selfassembler .
   ```

## Test Execution Issues

### Tests keep failing

**Error**: `Tests still failing after 5 iterations`

**Solutions**:

1. **Check test output**: Review the artifacts for actual errors
2. **Increase iterations**:
   ```yaml
   phases:
     test_execution:
       max_iterations: 10
   ```
3. **Skip to manual fix**: Resume and skip test execution
4. **Run tests manually**: Debug in the worktree

### No test command detected

**Error**: Test phase completes without running tests

**Solution**: Specify test command:
```yaml
commands:
  test: "pytest"  # or "npm test", etc.
```

## Checkpoint Issues

### Checkpoint not found

**Error**: `Checkpoint not found: checkpoint_xxx`

**Solutions**:

1. **List available checkpoints**:
   ```bash
   selfassembler --list-checkpoints
   ```

2. **Check checkpoint directory**: `~/.local/state/selfassembler/`

3. **Start fresh**: Run the workflow from the beginning

### Corrupted checkpoint

**Error**: `Invalid checkpoint data: ...`

**Solution**: Delete the corrupted checkpoint and start fresh:
```bash
rm ~/.local/state/selfassembler/checkpoint_xxx.json
```

## Notification Issues

### Webhook not receiving

**Solutions**:

1. Verify URL is correct and accessible
2. Check firewall/network settings
3. Test webhook manually:
   ```bash
   curl -X POST -H "Content-Type: application/json" \
     -d '{"test": true}' \
     https://your-webhook.example.com
   ```

### Slack notifications not working

**Solutions**:

1. Verify webhook URL is correct
2. Check Slack app permissions
3. Test webhook in Slack's webhook tester

## Getting Help

### Debug Mode

Run with verbose output:
```bash
selfassembler "Task" --name task --verbose
```

### Check Logs

- Workflow artifacts are in `./plans/`
- Checkpoints are in `~/.local/state/selfassembler/`

### Report Issues

If you encounter a bug:

1. Check existing issues on GitHub
2. Include:
   - SelfAssembler version
   - Python version
   - Error message
   - Steps to reproduce
3. Open an issue at https://github.com/selfassembler/selfassembler/issues
