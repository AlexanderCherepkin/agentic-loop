---
name: goal
description: Use when the user wants a one-shot, verifiable task executed with cheap worker + expensive verifier split. Handles `/goal <goal>` and plain-language goal requests by routing to `goal_planner_v2.md`, enforcing L1 trust default, cost guard, and adversarial verification with ≥2 critics before declaring the goal satisfied.
---

# /goal

> One-shot verifiable task execution.
>
> You name the finish line; `/goal` splits the work into a cheap `claude-haiku-4-5`
> evidence-gathering phase and an expensive `claude-opus-4-8` adversarial verification
> phase. The loop stops automatically when ≥2 independent critics agree the goal is
> met, or escalates to you if the budget or iteration limit is exhausted.
>
> Backed by: `goal_planner_v2.md`, `runtime/loop_engine/loop_verifier.py`,
> `runtime/loop_engine/loop_cost_estimator.py`, `control/loop_trust_levels.md`.

---

## Когда срабатывать

Активируй, когда пользователь:

- пишет `/goal ...` — явный вызов;
- говорит «убедись, что ...», «добейся, чтобы ...», «проверь, что ...»;
- просит закрыть одну конкретную цель с чётким критерием выполнения;
- просит «быстро оценить ...», «fast-critic ...».

**НЕ срабатывай:**

- если запрос — open-ended brainstorming / research без finish line;
- если запрос требует deploy, `git push`, `rm -rf`, DB migration, production secrets — это human-zone действия; `/goal` может их планировать, но не выполнять автономно;
- если пользователь просит recurring/scheduled execution — это `/loop`, а не `/goal`.

---

## 🛡 ГАРДЫ (выполнять ВСЕГДА)

### Гард 1 — Цель должна быть верифицируемой

Перед планированием убедись, что goal имеет чёткое pass/fail условие. Примеры:

- ✅ «все core-тесты зелёные и health check чистый»
- ✅ «ни один файл в `runtime/premium_design/` не использует Inter как primary font»
- ✅ «anti-slop gate проходит для `DESIGN.md`»
- ❌ «сделай сайт лучше» — слишком размыто; сначала уточни критерий.

Если критерий не дан — задай до 3 уточняющих вопросов, затем сформулируй criteria сам и покажи пользователю.

### Гард 2 — Trust level L1 по умолчанию

- Новый `/goal` всегда начинает с `L1` (read/report only).
- L2/L3 требуют явного повышения через `control/loop_trust_levels.md` и историю стабильности.
- Никогда не разрешай L3 для `git push`, deploy, `rm -rf`, DB migrations, production secrets — эти операции всегда остаются в human zone.

### Гард 3 — Cost guard

- Перед любыми LLM-вызовами оцени стоимость через `runtime/loop_engine/loop_cost_estimator.py`.
- Если estimated cost превышает `budget.max_cost_usd` или `budget.max_tokens` — abort и предложи сузить scope.
- Дефолтный бюджет: `max_cost_usd=2.0`, `max_tokens=200000`, `max_iterations=8`.

### Гард 4 — Adversarial verification

- Верификатор запускает ≥2 независимых critic.
- Goal считается выполненным только если ≥2 critic согласны (`approved=True`).
- Если consensus не достигнут — вернуться к `tooll_subagents/self_correction/plan_adjustment.md` или эскалировать человеку.

---

## 📋 Decision Flow

1. **Parse goal** — извлеки `goal` и опциональные `criteria` из запроса. Если criteria нет — выведи 1–3 верифицируемых критерия.
2. **Trust gate** — вызови `control/loop_trust_levels.md` с `current_trust_level=L1` (или из сессии). Зафиксируй `effective_trust_level` и `blocked_operations`.
3. **Cost estimate** — вызови `runtime/loop_engine/loop_cost_estimator.py` с предполагаемым preset или goal. Если `budget_ok=False` — остановись и предложи scope reduction.
4. **Build cheap worker phase** — запланируй parallel `claude-haiku-4-5` подзадачи для сбора evidence по каждому criterion. Используй read/search/audit/grep вместо дорогих LLM-вызовов.
5. **Run workers** — выполни подзадачи параллельно. Каждый worker возвращает `{criterion, passed, evidence, confidence}`.
6. **Verify** — передай результаты `runtime/loop_engine/loop_verifier.py`. Запроси ≥2 adversarial critics (`claude-opus-4-8`).
7. **Decision**:
   - `approved=True` и consensus ≥2 → goal satisfied. Запиши полезные выводы в `.agent_loop/CONSTRAINTS.md` через `runtime/loop_engine/constraints_manager.py`, если они reusable.
   - `approved=False` и `iteration_count < max_iterations` → route to `tooll_subagents/self_correction/plan_adjustment.md` и повтори с 4 шага.
   - `approved=False` и бюджет/итерации исчерпаны → escalate human.
8. **Report** — краткий итог: goal, criteria, verdict, стоимость, найденные issues, следующий шаг.
9. **Export** — предложи сохранить reusable workflow:
   - в `memory/wiki/` — автоматически;
   - в `.claude/skills/` — только после явного «да» / «ok».

---

## 🪤 Failure Modes

| Condition | Response |
|---|---|
| Goal отсутствует или не верифицируем | Спросить уточняющие вопросы; не запускать worker |
| Budget превышен | Abort; предложить сузить scope или увеличить budget |
| Trust gate блокирует requested level | Downgrade to L1/L2; вставить human approval gate |
| Verifier reject, итерации остались | Route to `plan_adjustment.md`; повторить |
| Verifier reject, итерации/бюджет кончились | Escalate human с полным evidence package |
| <2 critics согласны | Treat as rejection |
| Операция в human zone (push/deploy/rm/etc.) | Cap at L2; require `tooll_subagents/execution/human_approval.md` |
| Cost tracking недоступен | Estimate conservatively; логировать gap |

---

## ✅ Что `/goal` гарантирует

- Цель будет разбита на верифицируемые criteria.
- Большая часть работы сделана дёшевыми worker-моделями.
- Финальное решение принято дорогим verifier с adversarial consensus.
- Бюджет не превышен — cost guard abort до LLM-вызовов.
- Human-zone операции не выполняются автономно.
- Успешные workflow сохраняются в wiki; skill export требует explicit approval.

---

*Internal reference: [[loop-engine]] in `memory/wiki/tool/loop-engine.md`.*
