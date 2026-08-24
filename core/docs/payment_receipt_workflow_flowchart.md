# Payment Receipt Workflow Flowchart

This document contains the full operational flow for customer payment receipts. It complements `docs/system_documentation_en.md`.

## Legend

- Main status is stored on `PaymentRecord.status`.
- Finance registration is stored independently on `PaymentRecord.finance_status`.
- Counterparty review is stored independently from finance and commercial decisions.
- Every important transition must write `PaymentActivityLog` and create relevant `UserNotification`.
- Operational dashboards show records that need action. History pages show all authorized records.

## Status Reference

| Status/flag | Code/value | Dashboard behavior |
| --- | --- | --- |
| Under review | `pending` | visible to staff dashboards |
| Commercial review | `commercial_review` | visible to commercial dashboard |
| Temporary commercial registration | `temp_commercial` | visible as pending/follow-up commercial state when action is needed |
| Commercial registered | `approved` | removed from commercial dashboard unless returned/follow-up |
| Finance pending | `finance_status=None` | visible to finance dashboard when finance action is needed |
| Finance registered | `finance_status='finance_ok'` | removed from finance dashboard unless returned/follow-up |
| Returned to commercial | `returned_commercial` | visible to commercial dashboard |
| Returned to finance | `returned_finance` | visible to finance dashboard |
| Follow-up | `follow_up` | visible to relevant staff dashboards |
| Incomplete | `incomplete` | staff operations blocked; customer correction required |
| Rejected | `rejected` | locked; hidden from operational dashboards |
| Final approved | `final_approved` | completed; history only |

## Full Flow

```mermaid
flowchart TD
    A[Customer uploads payment receipt] --> B[Create/update PaymentRecord]
    B --> C[status = pending<br/>finance_status = None]
    C --> D[Save receipt files<br/>image or PDF]
    D --> E[Create PaymentActivityLog]
    E --> F[Notify staff<br/>color #DDF6D2]
    E --> G{SMS enabled and configured?}
    G -- Yes --> H[Send short SMS to customer]
    G -- No --> I[Skip SMS without blocking upload]

    C --> J{Commercial action}
    C --> K{Finance action}

    J --> J1[Commercial registers]
    J1 --> J1a[status = approved]
    J1a --> J1b[Log + notify<br/>color #B5F1CC]
    J1b --> CPQ{Counterparty assigned?}

    J --> J2[Commercial temporary registration]
    J2 --> J2a[status = temp_commercial]
    J2a --> J2b[Log + notify<br/>color #FEEAC9]
    J2b --> HX[History and/or dashboard depending on action need]

    J --> J3[Commercial returns to finance]
    J3 --> J3a[status = returned_finance]
    J3a --> J3b[Log + notify<br/>color #DBEAFE]
    J3b --> K

    J --> J4[Commercial marks follow-up]
    J4 --> J4a[status = follow_up]
    J4a --> J4b[Ask customer for statement or investigate bank/counterparty mismatch]
    J4b --> J4c[Log + notify<br/>color #FEEAC9]

    J --> J5[Commercial marks incomplete]
    J5 --> J5a[status = incomplete]
    J5a --> J5b[Staff operations blocked]
    J5b --> J5c[Customer edits/corrects receipt]
    J5c --> C

    J --> J6[Commercial rejects]
    J6 --> J6a[status = rejected]
    J6a --> J6b[Record locked and removed from operational dashboards]
    J6b --> J6c[Log + notify<br/>color #FECACA]

    CPQ -- No --> RQ{Finance registered?}
    CPQ -- Yes --> CP1[Show in counterparty dashboard]
    CP1 --> CP2{Counterparty decision}
    CP2 -- Approve --> CP3[counterparty_status = approved]
    CP3 --> CP4[Log + notify<br/>color #B5F1CC]
    CP4 --> RQ
    CP2 -- Return --> CP5[counterparty_status = returned]
    CP5 --> CP6[Log + notify<br/>color #FEEAC9]
    CP6 --> J4
    CP2 -- Reject --> CP7[counterparty_status = rejected]
    CP7 --> CP8[Reason required<br/>Log + notify color #FECACA]
    CP8 --> J4

    K --> K1[Finance registers payment]
    K1 --> K1a[finance_status = finance_ok]
    K1a --> K1b[finance_registered_at/by set]
    K1b --> K1c[Log + notify<br/>color #DDF6D2]
    K1c --> KQ{Need commercial recheck?}
    KQ -- Yes --> K2[Return to commercial]
    K2 --> K2a[status = returned_commercial]
    K2a --> K2b[Log + notify<br/>color #E9D5FF]
    K2b --> J
    KQ -- No --> RQ

    RQ -- Yes --> FA{Final approval required/available?}
    RQ -- No --> HX
    FA -- Yes --> FQ[Final approval queue]
    FQ --> FR[Authorized user approves]
    FR --> FR1[status = final_approved]
    FR1 --> FR2[Log + notify]
    FA -- No --> HX

    HX --> HIST[Visible in history for authorized users]
    J6c --> HIST
    FR2 --> HIST
```

## Decision Table

| Decision | Condition | Result |
| --- | --- | --- |
| Can customer upload receipt? | User is authenticated customer and form/files are valid | Receipt is saved and status becomes `pending`. |
| Is SMS sent after upload? | SMS settings are configured and enabled | Short SMS is sent; otherwise operation continues without SMS. |
| Can finance register? | User has finance access and record is not locked/rejected/incomplete | `finance_status='finance_ok'`. |
| Can commercial register? | User has commercial access and record is not locked/rejected/incomplete | `status='approved'`. |
| Can commercial return to finance? | Commercial user decides finance action is needed | `status='returned_finance'`, record returns to finance dashboard. |
| Can finance return to commercial? | Finance user decides commercial review is needed | `status='returned_commercial'`, record returns to commercial dashboard. |
| Can staff operate incomplete record? | `status='incomplete'` | No; only customer correction should continue the flow. |
| Can staff operate rejected record? | `status='rejected'` | No; record is locked and history-only. |
| Can counterparty see record? | `payment.counterparty` matches linked counterparty user | Record appears in counterparty dashboard. |
| Can counterparty operate? | Counterparty status is `active` | Approve/return/reject is allowed. |
| Should dashboard show record? | Current state requires action from current user's department | Show in dashboard. |
| Should history show record? | User is authorized by role/ownership | Show regardless of status. |

## Notification Color Table

| Event | Color |
| --- | --- |
| Customer upload | `#DDF6D2` |
| Finance registration | `#DDF6D2` |
| Commercial registration | `#B5F1CC` |
| Temporary commercial registration | `#FEEAC9` |
| Counterparty approval | `#B5F1CC` |
| Counterparty return/follow-up | `#FEEAC9` |
| Counterparty rejection | `#FECACA` |
| Payment rejection | `#FECACA` |
| Return to commercial | `#E9D5FF` |
| Return to finance | `#DBEAFE` |

## Customer Display Rules

```mermaid
flowchart LR
    A[Internal payment status] --> B{Is status actionable by customer?}
    B -- incomplete --> C[Show Incomplete<br/>customer must correct]
    B -- rejected --> D[Show Rejected]
    B -- approved --> E[Show Commercial registered]
    B -- final_approved --> F[Show Final approved]
    B -- pending/commercial_review/temp/returned/follow_up --> G[Show Under review]
```

## Dashboard Visibility Rules

```mermaid
flowchart TD
    A[PaymentRecord] --> B{User authorized?}
    B -- No --> C[Do not show]
    B -- Yes --> D{History page?}
    D -- Yes --> E[Show if ownership/role allows]
    D -- No --> F{Operational dashboard}
    F --> G{Record requires this department action?}
    G -- Yes --> H[Show]
    G -- No --> I[Hide from dashboard]
    F --> J{status rejected/final_approved?}
    J -- Yes --> I
    F --> K{status incomplete?}
    K -- Yes --> L[Hide from staff dashboard<br/>customer correction required]
```

