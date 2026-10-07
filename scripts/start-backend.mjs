import { spawn } from 'node:child_process'
import path from 'node:path'

const backendDirectory = path.resolve('vendor/social-auto-upload-web-ui/backend')
const pythonPath = path.join(backendDirectory, '.venv', 'Scripts', 'python.exe')
const child = spawn(pythonPath, ['app.py'], {
  cwd: backendDirectory,
  env: process.env,
  stdio: 'inherit',
})

child.on('exit', (code) => process.exit(code ?? 0))
child.on('error', (error) => {
  console.error(error)
  process.exit(1)
})
