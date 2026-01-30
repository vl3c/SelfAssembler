# Implementation Phase Prompt

Implement the following task: {{ task_description }}

{% if plan_file %}
Follow the implementation plan at: {{ plan_file }}
{% endif %}

## Guidelines

1. Follow the plan step by step
2. Write clean, well-documented code
3. Follow existing code conventions
4. Do NOT write tests yet (separate phase)
5. Do NOT commit changes (separate phase)

## Checklist

- [ ] All implementation steps completed
- [ ] Code follows project conventions
- [ ] No debug code or TODOs left
- [ ] Error handling is appropriate
- [ ] Edge cases are handled

## Progress Tracking

Mark completed items in the plan file as you progress.

Update the plan file with:
- [x] Completed steps
- Any deviations from the original plan
- Issues encountered and how they were resolved
