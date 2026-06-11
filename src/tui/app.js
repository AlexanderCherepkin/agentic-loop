'use strict';

const React = require('react');
const { Box, Text, useInput, useApp } = require('ink');
const { spawn } = require('child_process');
const readline = require('readline');
const path = require('path');

function App({ task, maxIterations, provider, model, sessionId, demo } = {}) {
  const { exit } = useApp();
  const isLive = Boolean(task || demo);

  const [status, setStatus] = React.useState('idle');
  const [phase, setPhase] = React.useState('');
  const [iteration, setIteration] = React.useState(0);
  const [agents, setAgents] = React.useState([]);
  const [logs, setLogs] = React.useState([]);
  const [safetyPassed, setSafetyPassed] = React.useState(0);
  const [safetyFailed, setSafetyFailed] = React.useState(0);
  const [result, setResult] = React.useState(null);
  const [elapsed, setElapsed] = React.useState(0);
  const [errorMsg, setErrorMsg] = React.useState('');

  useInput((input, key) => {
    if (input === 'q' || key.escape) {
      exit();
    }
  });

  React.useEffect(() => {
    if (!isLive) return;

    const start = Date.now();
    const cwd = path.resolve(__dirname, '..', '..');
    const pyArgs = ['-m', 'runtime.main'];
    if (task) pyArgs.push(task);
    pyArgs.push('--max-iterations', String(maxIterations || 5));
    if (provider) pyArgs.push('--provider', provider);
    if (model) pyArgs.push('--model', model);
    if (sessionId) pyArgs.push('--session-id', sessionId);
    if (demo) pyArgs.push('--demo');
    pyArgs.push('--json-stream');

    const child = spawn('python', pyArgs, {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    const rl = readline.createInterface({ input: child.stdout });

    rl.on('line', (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;

      let event = null;
      try {
        event = JSON.parse(trimmed);
      } catch {
        return;
      }

      if (event && event.t) {
        setElapsed(Date.now() - start);
        const t = event.t;
        const p = event.payload || {};

        if (t === 'phase.start') {
          setPhase(p.phase || '');
          setStatus('running');
        } else if (t === 'phase.end') {
          setPhase((p.phase || '') + ' ✓');
        } else if (t === 'agent.invoke') {
          setAgents((prev) => {
            const next = [...prev, {
              agent: p.agent_path || 'unknown',
              phase: p.phase || '',
              latency: p.latency_ms || 0,
              success: p.success,
              iteration: p.iteration || 0,
            }];
            return next.slice(-50);
          });
          setIteration(p.iteration || 0);
        } else if (t === 'audit') {
          setLogs((prev) => {
            const next = [...prev, {
              agent: p.agent || 'unknown',
              status: p.status || '',
              ts: event.ts || Date.now(),
            }];
            return next.slice(-20);
          });
          const st = String(p.status || '');
          if (st.includes('success')) {
            setSafetyPassed((n) => n + 1);
          } else if (st.includes('fail')) {
            setSafetyFailed((n) => n + 1);
          }
        }
        return;
      }

      if (event && event.status && event.session_id !== undefined) {
        setResult(event);
        setStatus(event.status);
        setElapsed(Date.now() - start);
      }
    });

    child.on('close', (code) => {
      if (code !== 0 && !result) {
        setStatus('failed');
      }
    });

    child.stderr.on('data', (d) => {
      const txt = d.toString();
      if (txt.includes('ERROR') || txt.includes('Traceback')) {
        setErrorMsg(txt.slice(0, 200));
      }
    });

    return () => {
      rl.close();
      child.kill();
    };
  }, [isLive, task, maxIterations, provider, model, sessionId, demo]);

  // Static dashboard when no live task is provided
  if (!isLive) {
    return (
      React.createElement(Box, { flexDirection: 'column', padding: 1 },
        React.createElement(Box, { marginBottom: 1 },
          React.createElement(Text, { bold: true, color: 'cyan' }, 'AGENTIC LOOP — Dashboard')
        ),
        React.createElement(Box, { marginBottom: 1 },
          React.createElement(Text, {}, 'Press '),
          React.createElement(Text, { bold: true }, 'q'),
          React.createElement(Text, {}, ' or '),
          React.createElement(Text, { bold: true }, 'Esc'),
          React.createElement(Text, {}, ' to quit')
        ),
        React.createElement(Box, { flexDirection: 'column' },
          React.createElement(Text, { color: 'gray' }, 'Commands:'),
          React.createElement(Text, { color: 'green' }, '  run <task>    — Execute a task through the ReAct pipeline'),
          React.createElement(Text, { color: 'green' }, '  status         — Show active sessions and stats'),
          React.createElement(Text, { color: 'green' }, '  validate       — Run all validators'),
          React.createElement(Text, { color: 'green' }, '  mcp-connect    — List connected MCP servers'),
          React.createElement(Text, { color: 'green' }, '  list-agents    — List all 157 agents'),
          React.createElement(Text, { color: 'gray' }, ''),
          React.createElement(Text, { color: 'gray' }, 'Architecture: 157 agents · 6 layers · 3-circuit safety'),
          React.createElement(Text, { color: 'gray' }, 'MCP Servers:  7 configured, stdio/SSE transport')
        )
      )
    );
  }

  const statusColor = status === 'success' ? 'green' : status === 'failed' ? 'red' : 'yellow';

  return (
    React.createElement(Box, { flexDirection: 'column', padding: 1 },
      React.createElement(Box, { marginBottom: 1 },
        React.createElement(Text, { bold: true, color: 'cyan' }, 'AGENTIC LOOP — Live Pipeline')
      ),
      React.createElement(Box, { marginBottom: 1 },
        React.createElement(Text, {}, 'Status: '),
        React.createElement(Text, { bold: true, color: statusColor }, status || 'running'),
        React.createElement(Text, {}, `  Phase: `),
        React.createElement(Text, { bold: true, color: 'white' }, phase || '-'),
        React.createElement(Text, {}, `  Iteration: ${iteration}  Time: ${elapsed}ms`)
      ),
      React.createElement(Box, { marginBottom: 1 },
        React.createElement(Text, { color: 'gray' }, `Safety: ${safetyPassed} passed / ${safetyFailed} failed`)
      ),
      React.createElement(Box, { flexDirection: 'column', marginBottom: 1 },
        React.createElement(Text, { bold: true, underline: true, color: 'white' }, 'Agents executed (last 12):'),
        agents.length === 0
          ? React.createElement(Text, { color: 'gray' }, '  Waiting for agents...')
          : agents.slice(-12).map((a, i) =>
              React.createElement(Text, { key: i, color: a.success ? 'green' : 'red' },
                `  ${a.phase.padEnd(18)} → ${a.agent.split('/').pop().slice(0, 40).padEnd(42)} ${Math.round(a.latency).toString().padStart(4)}ms`
              )
            )
      ),
      React.createElement(Box, { flexDirection: 'column', marginBottom: 1 },
        React.createElement(Text, { bold: true, underline: true, color: 'white' }, 'Audit log (last 10):'),
        logs.length === 0
          ? React.createElement(Text, { color: 'gray' }, '  Waiting for audit events...')
          : logs.slice(-10).map((l, i) =>
              React.createElement(Text, { key: i, color: String(l.status).includes('success') ? 'green' : 'red' },
                `  ${l.agent.split('/').pop().slice(0, 50).padEnd(52)} ${l.status.slice(0, 30)}`
              )
            )
      ),
      errorMsg && React.createElement(Box, { marginBottom: 1 },
        React.createElement(Text, { color: 'red' }, `Error: ${errorMsg}`)
      ),
      result && React.createElement(Box, { flexDirection: 'column', marginTop: 1 },
        React.createElement(Text, { bold: true, color: 'green' }, 'Result:'),
        React.createElement(Text, { color: 'white' }, result.response || JSON.stringify(result).slice(0, 600))
      ),
      React.createElement(Box, { marginTop: 1 },
        React.createElement(Text, { color: 'gray' }, 'Press q or Esc to quit')
      )
    )
  );
}

module.exports = { App };
