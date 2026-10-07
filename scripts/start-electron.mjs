import { spawn } from 'node:child_process'
import electronPath from 'electron'

import { desktopEnvironment } from '../apps/desktop/shared/desktop-env.js'

const child = spawn(electronPath, ['.'], {
  cwd: process.cwd(),
  env: desktopEnvironment(process.env),
  stdio: 'inherit',
})

child.on('exit', (code) => process.exit(code ?? 0))
child.on('error', (error) => {
  console.error(error)
  process.exit(1)
})
