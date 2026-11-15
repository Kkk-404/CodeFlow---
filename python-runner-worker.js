'use strict';

const pyodideRoot = new URL('./pyodide/', self.location.href);
const pyodideIndexURL = pyodideRoot.href;
const nativeFetch = self.fetch.bind(self);
const nativeImportScripts = self.importScripts.bind(self);
let activeRunId = '';

function send(type, text, phase) {
  self.postMessage({
    codeflowPython: true,
    id: activeRunId,
    type,
    phase: phase || '',
    text: String(text || '').slice(0, 1200)
  });
}

// Defense in depth: allow only same-origin runtime files. The worker response also
// carries CSP from codeflow_server.py, which blocks external connections/scripts.
const runtimeFetch = (input, init) => {
  const raw = typeof input === 'string' ? input : input && input.url;
  let url;
  try { url = new URL(raw || '', self.location.href); }
  catch (_) { return Promise.reject(new TypeError('Недопустимый адрес запроса.')); }
  if (url.origin !== self.location.origin || !url.pathname.startsWith(pyodideRoot.pathname)) {
    return Promise.reject(new TypeError('Из песочницы разрешена загрузка только локальных файлов среды Python.'));
  }
  return nativeFetch(input, init);
};
self.fetch = runtimeFetch;
try {
  if (typeof WorkerGlobalScope !== 'undefined' && WorkerGlobalScope.prototype) {
    Object.defineProperty(WorkerGlobalScope.prototype, 'fetch', {
      value: runtimeFetch, writable: false, configurable: false
    });
  }
} catch (_) {}

self.addEventListener('message', async event => {
  const data = event.data;
  if (!data || data.type !== 'run' || typeof data.id !== 'string' || typeof data.code !== 'string') return;
  activeRunId = data.id;
  if (data.code.length > 12000) {
    send('error', 'Код длиннее разрешённых 12 000 символов.');
    return;
  }
  if (typeof data.tests === 'string' && data.tests.length > 6000) {
    send('error', 'Блок проверок длиннее разрешённых 6 000 символов.');
    return;
  }

  try {
    send('status', 'Загружаю локальную среду Python 3.14…', 'loading');
    nativeImportScripts('./pyodide/pyodide.js');
    const pyodide = await self.loadPyodide({
      indexURL: pyodideIndexURL,
      stdout: text => send('stdout', text),
      stderr: text => send('stderr', text)
    });
    // The runtime is loaded; Python code must not create network channels or nested workers.
    try { self.importScripts = () => { throw new TypeError('Загрузка скриптов из песочницы отключена.'); }; } catch (_) {}
    for (const name of ['WebSocket', 'EventSource', 'XMLHttpRequest', 'Worker', 'SharedWorker', 'BroadcastChannel']) {
      try { Object.defineProperty(self, name, { value: undefined, writable: false, configurable: false }); } catch (_) {}
    }

    const inputText = String(data.stdin || '').slice(0, 2000).replace(/\r\n?/g, '\n');
    const inputLines = inputText === '' ? [] : inputText.split('\n');
    if (inputText.endsWith('\n')) inputLines.pop();
    let inputIndex = 0;
    pyodide.setStdin({ stdin: () => inputIndex < inputLines.length ? inputLines[inputIndex++] : undefined });
    send('status', 'Выполняю код…', 'running');
    await pyodide.runPythonAsync(data.code);
    const tests = typeof data.tests === 'string' ? data.tests.slice(0, 6000) : '';
    if (tests.trim()) {
      send('status', 'Запускаю дополнительные проверки…', 'testing');
      await pyodide.runPythonAsync(tests);
      send('done', 'Код и дополнительный блок проверок завершились без ошибок.');
    } else {
      send('done', 'Код выполнен. Чтобы засчитать урок, отдельно нажми «Проверить по критериям».');
    }
  } catch (error) {
    send('error', String(error && error.message ? error.message : error));
  }
});
