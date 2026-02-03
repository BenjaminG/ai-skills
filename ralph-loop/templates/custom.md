# Ralph Agent: {{GOAL}}

## Configuration

- **Backlog**: `backlog.json`
- **Progress**: `progress.txt`
- **Knowledge**: `knowledge.md`

## Your Task (One Iteration)

### Step 1: Load Context

1. Read `backlog.json` to get task list and status
2. Read `knowledge.md` to understand previous learnings

### Step 2: Determine State

Check the backlog:

- **If ALL tasks have `status: "completed"`** → Output `<promise>COMPLETE</promise>` and stop
- **If pending tasks exist** → Continue to Step 3

### Step 3: Select Target

Pick the FIRST task where `status: "pending"` (sorted by priority).
Mark it as `status: "in_progress"` in backlog.json.

### Step 4: Execute Task

<!-- TODO: Define task-specific steps here -->

1. Read relevant files
2. Perform the task
3. Validate the result

### Step 5: Validate

<!-- TODO: Define acceptance criteria here -->

**Acceptance Criteria:**
- [ ] Task completed successfully
- [ ] No errors introduced
- [ ] Validation checks pass

### Step 6: Update Files

**Update backlog.json:**
- Set task `status: "completed"`
- Add `completedAt` timestamp

**Update progress.txt:**
```
[datetime] - Completed: {task_name} | Status: success
```

**Update knowledge.md:**
```markdown
---

## {TaskName} (completed {date})

**Findings**: ...

**Notes**: ...
```

## Important Rules

- Process ONLY 1 task per iteration
- Update all tracking files after each task
- Document learnings in knowledge.md

## Completion

When all tasks have `status: "completed"`:

```
<promise>COMPLETE</promise>
```
