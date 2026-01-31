# Research Phase Prompt

Research task: {{ task_description }}

## Objectives

1. **Read project conventions**:
   - Look for: claude.md, CLAUDE.md, AGENTS.md, CONTRIBUTING.md, .claude/*
   - Understand coding standards, patterns, and constraints

2. **Find related code**:
   - Search for files related to this feature
   - Understand existing patterns and conventions
   - Note reusable utilities or components

3. **Identify dependencies**:
   - External packages needed
   - Internal modules to import
   - API contracts to follow

## Output

Write your findings to: {{ research_file }}

Format the research as markdown with clear sections:

```markdown
# Research: {{ task_name }}

## Project Conventions
- Coding standards
- File organization
- Testing approach

## Related Code
- Similar features
- Reusable components
- Patterns to follow

## Dependencies
- External packages
- Internal modules
- APIs to use

## Notes
- Potential issues
- Questions to resolve
```
