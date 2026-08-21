import {execFile, spawn} from 'node:child_process';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const siteDir = resolve(fileURLToPath(new URL('..', import.meta.url)));
const docusaurus = resolve(siteDir, 'node_modules/.bin/docusaurus');
const enUrl = 'http://localhost:3000/';
const children = [];

function run(args, extraEnv = {}) {
  const child = spawn(docusaurus, args, {
    cwd: siteDir,
    env: {...process.env, ...extraEnv},
    stdio: 'inherit',
  });
  children.push(child);
  child.on('exit', (code, signal) => {
    if (signal) {
      return;
    }
    for (const other of children) {
      if (other !== child && other.exitCode === null) {
        other.kill('SIGTERM');
      }
    }
    process.exit(code ?? 0);
  });
}

function shutdown() {
  for (const child of children) {
    if (child.exitCode === null) {
      child.kill('SIGTERM');
    }
  }
}

async function waitFor(url) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, {redirect: 'manual'});
      if (response.status < 500) {
        return;
      }
    } catch {
      // Server is not listening yet.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function openBrowser(url) {
  if (process.env.BROWSER === 'none') {
    return;
  }
  if (process.platform === 'darwin') {
    execFile('open', [url]);
    return;
  }
  if (process.platform === 'win32') {
    execFile('cmd', ['/c', 'start', url]);
    return;
  }
  execFile('xdg-open', [url]);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

run(['start', '--port', '3000', '--no-open']);

waitFor(enUrl)
  .then(() => {
    process.stdout.write(`\nDocumentation: ${enUrl}\n`);
    openBrowser(enUrl);
    run(['start', '--port', '3001', '--locale', 'ru', '--no-open'], {
      DOCUSAURUS_GENERATED_FILES_DIR_NAME: '.docusaurus-ru',
    });
  })
  .catch((error) => {
    console.error(error);
    shutdown();
    process.exit(1);
  });
