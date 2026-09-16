import type { Register } from 'claude-code'

import { COMMAND as PRS, register as registerPrs } from './prs'
import { COMMAND as WT, register as registerWt } from './wt'

/**
 * The plugin's one hooks module. One event may be hooked once without a
 * matcher per module, so `session.start` lives here and registers every
 * pane's command; each pane hooks its own matched events. The loader reads
 * `on` statically: it goes only to functions imported by name.
 */
export const register: Register = (on, options) => {
  on('session.start', async ($, e, next) => {
    await $.command.register(PRS)
    await $.command.register(WT)

    return next(e)
  })

  registerPrs(on, options)
  registerWt(on, options)
}
