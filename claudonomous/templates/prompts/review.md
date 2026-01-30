# Code Review Phase Prompt

Review the implementation for: {{ task_description }}

## Review Process

1. Get the diff: `git diff {{ base_branch }}...HEAD`

2. Review for:
   - Logic errors or bugs
   - Security issues (injection, XSS, CSRF, etc.)
   - Performance problems
   - Missing edge cases
   - Code style violations
   - Incomplete implementations
   - TODOs or debug code left in
   - Hardcoded values that should be configurable
   - Missing error handling

## Output

Write your review findings to: {{ review_file }}

## Review Format

```markdown
# Code Review: {{ task_name }}

## Summary
[Overall assessment - Good/Needs Work/Major Issues]

## Issues Found

### Critical
- [Issue description with file:line reference]
- Why it's critical
- Suggested fix

### Major
- [Issue description]
- Impact
- Suggested fix

### Minor
- [Issue description]

## Suggestions
- [Optional improvements not blocking merge]

## Security Checklist
- [ ] No hardcoded secrets
- [ ] Input validation present
- [ ] SQL injection protected
- [ ] XSS protected
- [ ] CSRF protected (if applicable)

## Verdict
[APPROVE / REQUEST_CHANGES / NEEDS_DISCUSSION]
```

## Guidelines

- Be constructive and specific
- Provide code examples for fixes when helpful
- Focus on actual issues, not style preferences
- Prioritize security and correctness
