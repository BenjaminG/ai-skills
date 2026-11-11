# The local-app doc and its scripts

What `setup-ai-skills` writes in the host repo, and the contract every reader (pr-demo, pr-shots,
pr-try, showcase) relies on. Every value comes from the repo or a proven run, never from this template.

```
docs/agents/local-app.md          facts, traps and the reason behind each
docs/agents/local-app/prepare.sh  make this checkout runnable
docs/agents/local-app/launch.sh   start one server, in the foreground
docs/agents/local-app/doctor.sh   is this instance worth driving?
docs/agents/local-app/cleanup.sh  undo what the flag and data recipes changed
docs/agents/local-app/screens/    the screen map: README index, one file per screen
```

**Worktrees.** A committed doc is in every worktree. An excluded one reaches a worktree only as a
copy made at its creation (worktrunk's `.worktreeinclude` / `wt step copy-ignored`, when it lists
`docs/agents`), so older worktrees have a stale copy or none. The main worktree
(`git worktree list | head -1`) then holds the reference copy: readers read it there and fix it there.

## Scripts

Each script is executable, starts with a usage comment, acts on the checkout it is run from
(`git rev-parse --show-toplevel` from the current directory, not from the script's path: the script
may sit in the main worktree while the PR runs in another), and knows nothing about herdr or tmux:
the reader decides where a server runs. Shared values (ports, Node path, log directory) go in a
sourced `common.sh`.

- **`prepare.sh`**: idempotent; brings a fresh pull, a branch switch or a new worktree to runnable:
  dependencies, `.env` files copied from the main worktree, every code generation step (all of them:
  a package's codegen missing from the app's own `generate` task is the classic trap), compiled
  locales, stale build caches removed (never the cache of a server that is running: it would break
  it). Cheap when nothing changed: stamp what each step last saw (the lockfile, the commit) and skip
  when it matches. Codegen that reads a schema the API writes at boot runs again after the API is up.
  Prints one line per step.
- **`launch.sh --list`** prints one line per server: `<name> <port> <timeout-s> <ready text>`.
  **`launch.sh <name>`** runs that server in the foreground and tees its output to
  `${TMPDIR:-/tmp}/local-app-<repo>/<name>.log`, truncated at start. Containers the servers need
  (database, cache) are checked first, with the command to start them when they are down.
- **`doctor.sh [url…]`**: read-only. One line per check, `ok` / `warn` / `FAIL`, exit 1 on any
  `FAIL`: containers up, each port listening from this checkout (`lsof -a -p <pid> -d cwd`), the
  API answers, the test account signs in and its session query succeeds (a login can set cookies
  while every page still bounces back to it), codegen newer than its schema. Then each `url`: loaded
  with `curl -L` and the test account's cookies, `FAIL` on a 4xx/5xx or on an error line that the
  server logs printed during the request (diff the log files before and after). A screen that
  answers 200 but renders the not-found page counts as a `FAIL` too: match the framework's marker
  (Next pages router: `"page":"/404"` in `__NEXT_DATA__`), never the not-found text, which the
  embedded translation bundle contains on every page. Say which screens it cannot judge (behind
  another persona's login).
- **`cleanup.sh`**: idempotent; reverts the files the flag recipes edit and restores data the
  recipes changed. Stops nothing: whoever started a server stops it.
- **Fixture finders** (optional, e.g. `find-fixture.sh <persona>`): read-only; pick a record from
  the current data at run time and print its login, its URL, and the start-state fix it still needs
  (a value the branch no longer knows, a redirect to turn off) as the command a `reset` runs.

## `local-app.md` sections

Short entries, each with its reason when the reason is not obvious. A command lives in a script; the
doc names the script.

1. **prepare**: what `prepare.sh` covers and why each step exists (the error each one prevents).
2. **launch**: the servers, their ports and URLs, the containers they need.
3. **doctor**: what `doctor.sh` checks; the start URLs worth passing it.
4. **auth**: login URL per app, the test account (the name of the env var or file holding a secret,
   never the secret), how to pass a second factor locally (a fixed code under a test env, a mail
   catcher URL).
5. **data**: the database shell command, where fixtures live, how to find a record to film, known
   bad records and how to fix them.
6. **flags**: where a feature flag resolves locally (remote service, defaults file, per-record field)
   and how to force one; `cleanup.sh` reverts it.
7. **gotchas**: traps a run met, one line each with its fix. Example: "Film locally: staging asks
   for SSO and an emailed code."
8. **screens**: pointer to `screens/README.md`.

## Screen map

`screens/README.md` indexes one file per screen or feature a user reaches. Each file has four H2s:
`Sub-features`, `How to get to it (user POV)`, `Driving it with Playwright MCP` (roles and accessible
names, not CSS), `Gotchas`. A precondition the seed data lacks goes in `Gotchas`; the recipe is never
weakened to pass. [`screens-example/`](screens-example/) shows the shape.
