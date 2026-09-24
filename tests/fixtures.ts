import type {
  CommandRunInput,
  On,
  RenderInput,
  SessionStartInput,
} from 'claude-code'
import { mock } from 'claude-code/testing'

export const PLUGIN = 'ai-skills'

export const SESSION: SessionStartInput = {
  surface: 'terminal',
  isInteractive: true,
  cwd: '/work',
}

/** `/<name>` typed with no arguments, fullscreen on a 160-column terminal. */
export const command = (name: string): CommandRunInput => ({
  command: name,
  args: '',
  origin: { kind: 'composer' },
  presentation: { isFullscreen: true, columns: 160 },
})

/** The pane `id` docked on a 160-column terminal, 80 columns of body. */
export const pane = (id: string): RenderInput<'Pane'> => ({
  component: 'Pane',
  surface: 'terminal',
  requestId: id,
  viewport: { columns: 160, rows: 40 },
  props: {
    title: id,
    isFocused: false,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
})

/**
 * The world beneath the plugin: a session in /work, one process answering
 * `stdout` (or failing with `stderr`), panes and prompt fills kept.
 */
export function world(on: On, process: { stdout?: string; stderr?: string; python3?: { stdout?: string; stderr?: string; exitCode?: number } }) {
  const runs: string[][] = []
  // Every file's mtime as `date -r` prints it (kept out of `runs`); a test moves it to say
  // "the file changed".
  const files = { mtimeMs: 1 }
  const opened: string[] = []
  const closed: string[] = []
  const filled: string[] = []
  const toasts: string[] = []
  const toolCalls: Record<string, unknown>[] = []

  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', ($, e) => ({ value: { command: e.name } }))

  on('process.run', ($, e) => {
    if (e.argv[0] === 'date') {
      return { value: { exitCode: 0, stdout: `${files.mtimeMs}\n`, stderr: '' } }
    }

    runs.push([...e.argv])

    const answer: { stdout?: string; stderr?: string; exitCode?: number } =
      process.python3 !== undefined && e.argv[0] === 'python3'
        ? process.python3
        : process

    return {
      value: {
        exitCode: answer.stderr === undefined ? 0 : (answer.exitCode ?? 1),
        stdout: answer.stdout ?? '',
        stderr: answer.stderr ?? '',
      },
    }
  })

  on('ui.open', ($, e) => {
    opened.push(e.id)

    return { value: undefined }
  })

  on('ui.close', ($, e) => {
    closed.push(e.id)

    return { value: undefined }
  })

  on('ui.invalidate', () => ({ value: undefined }))

  on('ui.toast', ($, e) => {
    toasts.push(e.text)

    return { value: undefined }
  })

  on('prompt.fill', ($, e) => {
    filled.push(e.text)

    return { isFilled: true }
  })

  on('tool.call', ($, e) => {
    toolCalls.push({ ...e })

    return { result: 'ok' }
  })

  const clock = mock.clock(on)

  return { runs, opened, closed, filled, toasts, toolCalls, clock, files }
}

/** A rendered tree's text as it reads: strings and Button labels, in order. */
export function textOf(tree: unknown): string {
  if (typeof tree === 'string' || typeof tree === 'number') {
    return String(tree)
  }

  if (Array.isArray(tree)) {
    return tree.map(textOf).join('')
  }

  if (typeof tree !== 'object' || !tree) {
    return ''
  }

  const props: unknown = Reflect.get(tree, 'props')
  const label: unknown =
    typeof props === 'object' && props ? Reflect.get(props, 'label') : ''

  return `${typeof label === 'string' ? label : ''}${textOf(Reflect.get(tree, 'children') ?? [])}`
}
