# Novamind Scenario Runner Results

_Generated: 2026-10-22 19:52 UTC_

## Scenario Results

| Scenario | Score | Level | Decision | Hold? | Released? | Escalated? | Invariants | Latency ms |
|---|---|---|---|---|---|---|---|---|
| S1_low | 0 | low | clear | no | no | no | PASS | 26 |
| S2_moderate_me | 30 | moderate | release | no | yes | no | PASS | 41 |
| S3_moderate_not_me | 30 | moderate | hold_not_me | yes | no | no | PASS | 40 |
| S4_high | 80 | high | hold_escalate | yes | no | yes | PASS | 75 |
| S5_repeat_approvals | 50 | moderate | release, release, escalate_on_approval | no | no | yes | PASS | 135 |
| S6_no_reply | 30 | moderate | no_reply_hold | yes | no | yes | PASS | 35 |
| S7_thin_baseline | 35 | moderate | release | no | yes | no | PASS | 37 |
| S8_scam_reply | 30 | moderate | unverified_escalate | yes | no | yes | PASS | 50 |

_All invariants passed._

