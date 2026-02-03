---
name: quality
description: Quality gate review before merging. Reviews branch changes against React/Next.js best practices, SOLID principles, and removes AI code slop.
---

# Quality Gate Review

Run comprehensive quality checks on current branch changes before merging.

## Process

1. Get diff against main branch: `git diff main...HEAD`
2. Run `/vercel-react-best-practices` review on the diff
3. Run `/applying-solid-principles` review on the diff
4. Run `/code-slop` to identify and remove AI-generated patterns

## Output Format

```
## Quality Gate Report

### React/Next.js Best Practices
- [violations found or ✅ pass]

### SOLID Principles
- [violations found or ✅ pass]

### Code Slop Removal
- [changes made or ✅ clean]

### Summary
[1-3 sentence overall assessment]
```

Execute each review in sequence, collecting findings before producing the final report.
