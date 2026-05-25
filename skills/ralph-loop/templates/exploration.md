# Ralph Agent: {{GOAL}}

## Configuration

- **Target codebase**: `$TARGET_PATH`
- **Backlog**: `backlog.json` (files/modules to explore)
- **Knowledge**: `knowledge.md` (accumulated findings)
- **Dependency graph**: `dependency-graph.json` (optional)
- **Progress**: `progress.txt`

## Your Task (One Iteration)

### Step 1: Load Context

1. Read `backlog.json` to get exploration targets
2. Read `knowledge.md` to understand what's been discovered
3. Read `dependency-graph.json` if it exists

### Step 2: Determine State

Check the backlog:

- **If ALL targets have `status: "explored"`** → Output `<promise>COMPLETE</promise>` and stop
- **If unexplored targets exist** → Continue to Step 3

### Step 3: Select Target

Pick the FIRST target where `status: "pending"` from the backlog.
Mark it as `status: "in_progress"`.

### Step 4: Explore Target

Read the target file/module. Extract:

1. **Purpose**: What does this file/module do? (1-2 sentences)
2. **Imports**: What does it depend on?
3. **Exports**: What does it provide to others?
4. **Key Logic**: Main functionality, business rules
5. **API Calls**: Any external service calls
6. **Patterns**: Notable patterns or anti-patterns

### Step 5: Discover Dependencies

For each import/dependency:
- If it's within scope and not yet in backlog → Add as new target
- Track the relationship in dependency-graph.json

**Exclude:**
- External packages (node_modules)
- Test files (unless explicitly in scope)
- Generated files

### Step 6: Update dependency-graph.json

```json
{
  "nodes": [
    {
      "id": "path/to/file.ts",
      "type": "component|service|util|model|route",
      "explored": true,
      "summary": "Brief description"
    }
  ],
  "edges": [
    {
      "from": "source/file.ts",
      "to": "imported/file.ts",
      "type": "import|renders|extends|calls"
    }
  ]
}
```

### Step 7: Update Files

**Update backlog.json:**
- Set target `status: "explored"`
- Add newly discovered targets as `status: "pending"`

**Update progress.txt:**
```
[datetime] - Explored: {target} | New deps: {count} | Total unexplored: {count}
```

**Update knowledge.md:**
```markdown
---

## {FilePath} (explored {date})

**Type**: component/service/util/model/route

**Purpose**: {1-2 sentences}

**Key Findings**:
- {finding 1}
- {finding 2}

**Dependencies Added**: {list of new targets}
```

## Important Rules

- Explore ONLY 1 target per iteration
- Always read the file before marking as explored
- Preserve all existing data when updating JSON
- Use relative paths as identifiers

## Completion

When all targets have `status: "explored"`:

```
<promise>COMPLETE</promise>
```
