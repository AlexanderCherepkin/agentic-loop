import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

// Integration adapter: injects the premium-design Anti-Slop skill into a
// local Open Design (nexu-io) desktop instance via its local API.
//
// Usage:
//   node open-design-integrator.mjs
//   node open-design-integrator.mjs --port 8123 --skill ./.claude/skills/premium-design.skill.md
//
// Requires Open Design Desktop to be running and listening on the configured port.

const args = process.argv.slice(2);
function getArg(flag, fallback) {
  const idx = args.indexOf(flag);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : fallback;
}

const skillPath = path.resolve(getArg('--skill', './.claude/skills/premium-design.skill.md'));
const port = getArg('--port', '8123');
const OPEN_DESIGN_API = `http://127.0.0.1:${port}/api/v1/skills/register`;

if (!fs.existsSync(skillPath)) {
  console.error(`❌ Skill file not found: ${skillPath}`);
  console.error('Make sure premium-design.skill.md is in .claude/skills/');
  process.exit(1);
}

const skillContent = fs.readFileSync(skillPath, 'utf-8');

// Extract the 44-rule Anti-Slop block so we do not flood Open Design with the
// whole markdown file (frontmatter + intro stay lightweight).
const rulesMatch = skillContent.match(/## 02\. Спецификация 44 запретов[\s\S]*?## 03\./);
const rulesText = rulesMatch ? rulesMatch[0] : skillContent;

const payload = {
  name: 'premium-design-anti-slop',
  description: 'Premium UI/UX QA filter with 44 deterministic anti-slop rules',
  version: '1.0.0',
  global_trigger: true,
  system_prompt_injection: rulesText,
  config_matrix: {
    variance: 0.5,
    density: 0.3,
    motion: 0.5,
  },
};

console.log('⏳ Registering Anti-Slop Engine in Open Design...');
console.log(`   endpoint: ${OPEN_DESIGN_API}`);
console.log(`   skill:    ${skillPath}`);

try {
  const response = await fetch(OPEN_DESIGN_API, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (response.ok) {
    const data = await response.json().catch(() => ({}));
    console.log('✅ Anti-Slop skill registered in local Open Design instance.');
    console.log('   Every connected CLI agent will now inherit the 44-rule filter.');
    if (data.id) {
      console.log(`   registered id: ${data.id}`);
    }
  } else {
    const errText = await response.text();
    console.error('❌ Open Design API error:', errText);
    process.exit(1);
  }
} catch (error) {
  console.error('❌ Could not connect to Open Design.');
  console.error('   Make sure the Open Design Desktop app is running and listening', port);
  console.error('   Details:', error.message);
  process.exit(1);
}
