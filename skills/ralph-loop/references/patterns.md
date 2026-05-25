# Ralph Loop Patterns Reference

Common patterns and best practices for designing effective Ralph loops.

## Backlog Design Patterns

### Priority-Based Processing

Simple numeric priority where lower = higher priority:

```json
{
  "tasks": [
    { "id": "critical-1", "priority": 1, "status": "pending" },
    { "id": "normal-1", "priority": 10, "status": "pending" },
    { "id": "low-1", "priority": 100, "status": "pending" }
  ]
}
```

### Tier-Based Processing

Group tasks into tiers for staged rollout:

```json
{
  "tasks": [
    { "id": "easy-1", "tier": 1, "priority": 1, "notes": "Quick wins" },
    { "id": "medium-1", "tier": 2, "priority": 1, "notes": "Core work" },
    { "id": "hard-1", "tier": 3, "priority": 1, "notes": "Complex" }
  ]
}
```

### Dependency-Based Processing

Tasks with explicit dependencies:

```json
{
  "tasks": [
    { "id": "base", "depends_on": [], "status": "pending" },
    { "id": "feature-a", "depends_on": ["base"], "status": "blocked" },
    { "id": "feature-b", "depends_on": ["base", "feature-a"], "status": "blocked" }
  ]
}
```

Prompt logic:
```markdown
### Step 3: Select Target

1. Find all tasks where `status: "pending"`
2. Filter to only those with all dependencies completed
3. Pick the one with lowest priority number
```

## Iteration Patterns

### Single-File Focus

Process one file per iteration (most common):

```markdown
### Step 3: Select Target
Pick the FIRST file where `status: "pending"`.
Process only THIS file in this iteration.
```

### Batch Processing

Process multiple related items together:

```markdown
### Step 3: Select Target
Pick all tasks in the same `group` where `status: "pending"`.
Process them together as a batch.
```

### Discovery-Driven

Start with seed tasks, discover more during execution:

```markdown
### Step 5: Discover Dependencies
For each import in the current file:
- If not in backlog → Add as new pending task
- Track the relationship
```

## Validation Patterns

### Build Validation

```markdown
### Validation
```bash
pnpm build
pnpm typecheck
```

**Acceptance Criteria:**
- [ ] Build passes
- [ ] No type errors
```

### Test Validation

```markdown
### Validation
```bash
pnpm test -- --passWithNoTests
```

**Acceptance Criteria:**
- [ ] All tests pass
- [ ] No regressions
```

### Manual Checkpoint

```markdown
### Validation

At this point, manually verify:
- [ ] Visual appearance matches expectation
- [ ] Behavior is correct

If validation fails, mark task as `status: "blocked"` with notes.
```

## Progress Tracking Patterns

### Simple Log

```
[datetime] - Completed: {task} | Status: success
```

### Metrics Log

```
[datetime] - Completed: {task} | Duration: {time} | Files: {count} | LOC: {lines}
```

### Stats Summary

At the end of progress.txt, maintain running stats:

```
## Summary
- Total tasks: 50
- Completed: 23
- Remaining: 27
- Success rate: 100%
```

## Knowledge Accumulation Patterns

### Pattern Library

Document reusable patterns:

```markdown
## Discovered Patterns

### Pattern: API Response Handling
When migrating API calls:
1. Extract response type
2. Add error handling
3. Use consistent naming

**Example:**
```typescript
// Before: inline handling
// After: typed response with error boundary
```

### Issue Tracker

Track recurring issues:

```markdown
## Known Issues

### Issue: Circular Dependencies
**Frequency**: 3 occurrences
**Solution**: Extract shared types to separate file
**Files affected**: auth.ts, user.ts, session.ts
```

## Exit Condition Patterns

### All Tasks Complete

```markdown
## Completion
When all tasks have `status: "completed"`:
<promise>COMPLETE</promise>
```

### All Nodes Explored (Graph)

```markdown
## Completion
When ALL nodes in dependency-graph.json have `explored: true`:
<promise>COMPLETE</promise>
```

### Coverage Threshold

```markdown
## Completion
When test coverage reaches 80%:
<promise>COMPLETE</promise>
```

### Manual Approval

```markdown
## Completion
When user confirms migration is ready:
<promise>COMPLETE</promise>

Note: This requires running with user interaction enabled.
```

## Error Handling Patterns

### Fail Fast

```markdown
### On Error
If any step fails:
1. Mark task as `status: "blocked"`
2. Add error details to `notes`
3. Continue to next task

Do NOT output `<promise>COMPLETE</promise>` if blocked tasks exist.
```

### Retry Logic

```markdown
### On Error
If validation fails:
1. Attempt fix based on error message
2. Re-run validation
3. If still failing after 2 attempts, mark as `blocked`
```

### Skip and Continue

```markdown
### On Error
If task cannot be completed:
1. Mark as `status: "skipped"`
2. Add reason to `notes`
3. Continue with next task

Skipped tasks don't block completion.
```

## Anti-Patterns to Avoid

### Context Overflow

❌ Loading entire codebase into prompt
✅ Load only current task's relevant files

### Stateless Iterations

❌ Not reading previous state
✅ Always load backlog.json and knowledge.md first

### Silent Failures

❌ Continuing when validation fails
✅ Explicitly handle and track failures

### Unbounded Discovery

❌ Adding every discovered file to backlog
✅ Filter to only relevant scope

### Missing Completion Marker

❌ Forgetting `<promise>COMPLETE</promise>`
✅ Always output marker when done
