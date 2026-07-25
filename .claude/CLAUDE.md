# system-architect
- **system-architect** (`.claude/skills/system-architect/SKILL.md`) - highest-priority protocol for building websites, web apps, SaaS, frontend/backend, or any digital product. Trigger: `/system-architect` or any request to build/design/redesign a site, app, frontend, backend, or product.
When the user asks to build/design/redesign a website, web app, SaaS, mobile app, frontend, backend, or any digital product, invoke the Skill tool with `skill: "system-architect"` before doing anything else. If the request also mentions premium/anti-slop concerns, continue with the `anti-slop` skill after `system-architect`.

# graphify
- **graphify** (`.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.

# anti-slop
- **anti-slop** (`.claude/skills/anti-slop/SKILL.md`) - prevent AI-slop in generated websites and design systems. Trigger: `/anti-slop` or any request to generate/redesign a website, landing page, or web app.
When the user types `/anti-slop` or asks to build/redesign a site, invoke the Skill tool with `skill: "anti-slop"` before doing anything else.

# goal
- **goal** (`.claude/skills/goal/SKILL.md`) - one-shot verifiable task execution via cheap worker + expensive verifier split. Trigger: `/goal` or a plain-language verifiable goal request.
When the user types `/goal` or asks for a verifiable one-shot goal (e.g., "make sure all core tests pass"), invoke the Skill tool with `skill: "goal"` before doing anything else.
