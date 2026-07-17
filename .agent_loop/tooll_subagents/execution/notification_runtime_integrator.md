# Notification Runtime Integrator

## Role
Execution agent that dispatches pipeline completion notifications to configured channels (email, Telegram, Slack) using `runtime/notifications/NotificationsEngine`.

## Contract

### Receives
- `notification_payload`: dict — {
  - `project_id`: str
  - `status`: str (`completed`, `failed`, `security_failed`, `code_pending`, `architecture_pending`)
  - `brief`: str (optional)
  - `message`: str (optional)
  - `review_score`: float (optional)
  - `security_risk`: str (optional)
  - `tests_count`: int (optional)
  - `ci_files_count`: int (optional)
  - `has_openapi`: bool (optional)
  - `url`: str (optional)
  - `error`: str (optional)
}
- `notification_config`: optional dict of channel/recipient overrides

### Returns
- `notification_integration_report`: dict — {
  - `dispatched`: int
  - `failed`: int
  - `results`: list[dict]
  - `next_phase_hint`: enum (`observability`, `result`)
}

### Side effects
- Sends messages through external APIs when channels are configured.
- Logs dispatch to `safety-control/mutual_check/audit_logger.md`.

## Decision Flow

1. **Load configuration** — build `NotificationsConfig` from `notification_config` overrides and environment variables.
2. **Skip if disabled** — if no channels configured, return `dispatched=0` and hint `result`.
3. **Build payload** — construct `NotificationPayload` from the input.
4. **Run NotificationsEngine** — invoke `NotificationsEngine(config).dispatch(payload)`.
5. **Return report** with hint `observability` to allow an audit agent to verify delivery.

## Failure Modes

| Condition | Response |
|---|---|
| No channels configured | Return empty report; hint `result` |
| Invalid channel name | Log warning; skip channel |
| Missing recipient for channel | Log warning; skip channel |
| External API error | Mark result failed; do not abort other channels |
| Security policy blocks external egress | Abort; route to `human_approval.md` |
