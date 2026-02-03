# Ralph Agent: {{GOAL}}

## Configuration

- **Target codebase**: `$TARGET_PATH`
- **Backlog**: `backlog.json` (items to refactor)
- **Progress**: `progress.txt`
- **Knowledge**: `knowledge.md`

## Your Task (One Iteration)

### Step 1: Load Context

1. Read `backlog.json` to get refactoring targets
2. Read `knowledge.md` to understand patterns applied

### Step 2: Determine State

Check the backlog:

- **If ALL items have `status: "refactored"`** → Output `<promise>COMPLETE</promise>` and stop
- **If pending items exist** → Continue to Step 3

### Step 3: Select Target

Pick the FIRST item where `status: "pending"` (sorted by priority).
Mark it as `status: "in_progress"` in backlog.json.

### Step 4: Analyze Current State

Read the target code to understand:
1. **Current implementation**: How does it work now?
2. **Issues**: What problems need fixing?
3. **Dependencies**: What depends on this code?
4. **Tests**: Are there existing tests?

### Step 5: Plan Refactoring

Determine the safest approach:
- Preserve external behavior
- Maintain backward compatibility
- Make incremental changes
- Keep commits atomic

### Step 6: Execute Refactoring

Apply the refactoring:
1. Make the changes
2. Update any affected imports
3. Fix any type errors
4. Run linting/formatting

### Step 7: Validate

Run validation:
```bash
# Type check
pnpm typecheck

# Lint
pnpm lint

# Tests
pnpm test
```

**Acceptance Criteria:**
- [ ] External behavior unchanged
- [ ] All tests pass
- [ ] No new type errors
- [ ] No new lint errors
- [ ] Code is cleaner/more maintainable

### Step 8: Update Files

**Update backlog.json:**
- Set item `status: "refactored"`
- Add `changes` summary

**Update progress.txt:**
```
[datetime] - Refactored: {item} | Changes: {summary} | Status: success
```

**Update knowledge.md:**
```markdown
---

## {ItemName} (refactored {date})

**Changes Made**:
- {change 1}
- {change 2}

**Pattern Applied**:
- {pattern name/description}

**Before/After**:
```typescript
// Before
{old code snippet}

// After
{new code snippet}
```

**Notes**:
- {anything notable}
```

## Important Rules

- Refactor ONLY 1 item per iteration
- Preserve external behavior
- Run tests after each change
- Document patterns for future iterations

## Completion

When all items have `status: "refactored"`:

```
<promise>COMPLETE</promise>
```
