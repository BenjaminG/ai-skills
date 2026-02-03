# Ralph Agent: {{GOAL}}

## Configuration

- **Source**: `$SOURCE_PATH`
- **Target**: `$TARGET_PATH`
- **Backlog**: `backlog.json`
- **Progress**: `progress.txt`
- **Knowledge**: `knowledge.md`

## Your Task (One Iteration)

### Step 1: Load Context

1. Read `backlog.json` to get migration items and status
2. Read `knowledge.md` to understand previous patterns and learnings

### Step 2: Determine State

Check the backlog:

- **If ALL items have `status: "completed"`** → Output `<promise>COMPLETE</promise>` and stop
- **If pending items exist** → Continue to Step 3

### Step 3: Select Target

Pick the FIRST item where `status: "pending"` (sorted by priority).
Mark it as `status: "in_progress"` in backlog.json.

### Step 4: Analyze Source

Read the source item to understand:
1. **Structure**: How is it currently implemented?
2. **Dependencies**: What does it depend on?
3. **Usage patterns**: How is it used in the codebase?

### Step 5: Create Migration

1. Create the new implementation in the target location
2. Match the existing API/interface exactly
3. Apply patterns from knowledge.md if applicable

### Step 6: Validate

Run validation checks:
```bash
# Build/compile check
pnpm build

# Type check
pnpm typecheck

# Tests (if applicable)
pnpm test
```

**Acceptance Criteria:**
- [ ] New implementation has same interface as source
- [ ] All existing usages would work with new implementation
- [ ] Build passes without errors
- [ ] TypeScript compiles without errors

### Step 7: Update Files

**Update backlog.json:**
- Set item `status: "completed"`
- Add `completedAt` timestamp
- Add any notes about the migration

**Update progress.txt:**
```
[datetime] - Migrated: {item_name} | Status: success | Notes: {any_notes}
```

**Update knowledge.md:**
```markdown
---

## {ItemName} (migrated {date})

**Migration Notes**:
- {key findings}

**Patterns Applied**:
- {reusable patterns}

**Challenges**:
- {any issues encountered}
```

## Important Rules

- Migrate ONLY 1 item per iteration
- Match the existing API exactly - no breaking changes
- Preserve all functionality and behavior
- Document any edge cases in knowledge.md

## Completion

When all items have `status: "completed"`:

```
<promise>COMPLETE</promise>
```
