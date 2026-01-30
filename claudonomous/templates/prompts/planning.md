# Planning Phase Prompt

Create a detailed implementation plan for: {{ task_description }}

{% if research_file %}
Reference the research at: {{ research_file }}
{% endif %}

## Output

Write the plan to: {{ plan_file }}

## Plan Format

```markdown
# Implementation Plan: {{ task_name }}

## Summary
[1-2 sentence overview of what will be implemented]

## Files to Modify/Create
- [ ] path/to/file.ext - [brief description of changes]

## Implementation Steps

### Step 1: [Name]
- **Description**: What this step accomplishes
- **Files involved**: List of files
- **Acceptance criteria**: How to verify this step is complete

### Step 2: ...

## Testing Strategy
- [ ] Unit tests for...
- [ ] Integration tests for...

## Risks/Blockers
- Any potential issues or dependencies
```

## Guidelines

1. Be specific about which files to modify
2. Include clear acceptance criteria for each step
3. Consider edge cases in testing strategy
4. Identify potential risks upfront
