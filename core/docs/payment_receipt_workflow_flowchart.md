# Payment Receipt Workflow Flowchart

This document contains the full operational flow for customer payment receipts. It complements `docs/system_documentation_en.md`.

Last updated: 2026-09-05

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
| Commercial review | `commercial_review` | visible to commercial dashboard; set automatically on creation |
| Temporary commercial registration | `temp_commercial` | visible in "In Progress" commercial dashboard; visible to finance if `finance_ok` |
| Commercial registered | `approved` | removed from commercial dashboard unless returned or voided |
| Finance pending | `finance_status=None` | visible to finance dashboard when finance action is needed |
| Finance registered | `finance_status='finance_ok'` | removed from finance dashboard unless returned |
| Returned to commercial | `returned_commercial` | visible to commercial dashboard |
| Returned to finance (regular) | `returned_finance` + `is_void_return=False` | visible to finance dashboard |
| Returned to finance (void) | `returned_finance` + `is_void_return=True` | visible only in Voided Documents dashboard |
| Incomplete | `incomplete` | staff operations blocked; customer correction required |
| Rejected | `rejected` | locked; hidden from operational dashboards |
| Voided | `void_confirmed` | permanently removed from all operational dashboards |
| Final approved | `final_approved` | completed; history only |
| Admin review needed | `needs_admin_review=True` | visible in Admin Review Queue (superuser only) |
| Admin edited | `is_admin_edited=True` | orange triangle shown in table row corners |

## Full Flow

```mermaid
flowchart TD
    A[Customer uploads payment receipt] --> B[Create/update PaymentRecord]
    B --> C[status = commercial_review<br/>finance_status = None]
    C --> D[Save receipt files<br/>image or PDF]
    D --> E[Create PaymentActivityLog]
    E --> F[Notify staff<br/>color #DDF6D2]
    E --> G{SMS enabled?}
    G -- Yes --> H[Send short SMS to customer]
    G -- No --> I[Skip SMS without blocking]

    C --> J{Commercial action}
    C --> K{Finance action}

    J --> J1[Commercial registers]
    J1 --> J1a[status = approved]
    J1a --> J1b[Log + notify color #B5F1CC]
    J1b --> CPQ{Counterparty assigned?}

    J --> J2[Temporary commercial registration]
    J2 --> J2a[status = temp_commercial]
    J2a --> J2b[Log + notify color #FEEAC9 if finance registered]
    J2b --> TCDASH[In Progress dashboard]

    TCDASH --> TC1{Action from temp_commercial}
    TC1 --> TC1a[Register commercial → approved]
    TC1 --> TC1b[Void return to finance<br/>requires finance_ok]
    TC1 --> TC1c[Incomplete / Reject<br/>notify finance if registered]
    TC1 --> TC1d[Request admin review]

    J1a --> AP1{Action from approved}
    AP1 --> AP1a[Temp commercial → temp_commercial<br/>notify finance if registered]
    AP1 --> AP1b[Void return to finance<br/>requires finance_ok]
    AP1 --> AP1c[Incomplete / Reject]
    AP1 --> AP1d[Request admin review]

    TC1b --> VD[returned_finance + is_void_return=True]
    AP1b --> VD
    VD --> VDASH[Finance — Voided Documents dashboard]
    VDASH --> VF[Finance confirms void]
    VF --> VF1{finance_status == finance_ok?}
    VF1 -- Yes --> VF2[Auto-reverse finance registration<br/>Log ACTION_FINANCE_VOID_REVERSED]
    VF1 -- No --> VF3[Skip reversal]
    VF2 --> VOID[status = void_confirmed<br/>Log + notify commercial + customer #FECACA]
    VF3 --> VOID

    TC1d --> ADQ[needs_admin_review=True]
    AP1d --> ADQ
    ADQ --> ADASH[Superuser — Admin Review Queue]
    ADASH --> ADEDIT[Full edit form<br/>all fields + status flags]
    ADEDIT --> ADLOG[Log all changes before/after<br/>is_admin_edited=True<br/>notify commercial + finance #FEF3C7]
    ADLOG --> ADTRI[Orange triangle on row in tables]
    ADTRI --> J

    J --> J3[Commercial returns to finance]
    J3 --> J3a[status = returned_finance<br/>is_void_return=False]
    J3a --> J3b[Log + notify color #DBEAFE]
    J3b --> K

    J --> J4[Commercial marks incomplete]
    J4 --> J4a[status = incomplete]
    J4a --> J4b[Staff operations blocked]
    J4b --> J4c[Customer edits/corrects receipt]
    J4c --> C

    J --> J5[Commercial rejects]
    J5 --> J5a[status = rejected]
    J5a --> J5b[Record locked]
    J5b --> J5c[Log + notify color #FECACA]

    CPQ -- No --> RQ{Finance registered?}
    CPQ -- Yes --> CP1[Show in counterparty dashboard]
    CP1 --> CP2{Counterparty decision}
    CP2 -- Approve --> CP3[counterparty_status = approved]
    CP3 --> CP4[Log + notify color #B5F1CC]
    CP4 --> RQ
    CP2 -- Return --> CP5[counterparty_status = returned]
    CP5 --> CP6[Log + notify color #FEEAC9]
    CP6 --> J
    CP2 -- Reject --> CP7[counterparty_status = rejected]
    CP7 --> CP8[Reason required<br/>Log + notify color #FECACA]
    CP8 --> J

    K --> K1[Finance registers payment]
    K1 --> K1a[finance_status = finance_ok]
    K1a --> K1b[finance_registered_at/by set]
    K1b --> K1c[Log + notify color #DDF6D2]
    K1c --> KQ{Need commercial recheck?}
    KQ -- Yes --> K2[Return to commercial]
    K2 --> K2a[status = returned_commercial]
    K2a --> K2b[Log + notify color #E9D5FF]
    K2b --> J
    KQ -- No --> RQ

    RQ -- Yes --> FA{Final approval required?}
    RQ -- No --> HX
    FA -- Yes --> FQ[Final approval queue]
    FQ --> FR[Authorized user approves]
    FR --> FR1[status = final_approved]
    FR1 --> FR2[Log + notify]
    FA -- No --> HX

    HX --> HIST[Visible in history for authorized users]
    J5c --> HIST
    FR2 --> HIST
    VOID --> HIST
```

## Decision Table

| Decision | Condition | Result |
| --- | --- | --- |
| Can customer upload receipt? | Authenticated customer; valid form/files | Status becomes `commercial_review`. |
| Is SMS sent after upload? | SMS settings are configured and enabled | Short SMS sent; otherwise operation continues. |
| Can finance register? | User has finance access; record is not locked/rejected/incomplete/voided | `finance_status='finance_ok'`. |
| Can commercial register? | User has commercial access; not locked/rejected | `status='approved'`. |
| Can commercial set temp? | From `commercial_review` or `approved` | `status='temp_commercial'`. |
| Can commercial void? | From `temp_commercial` or `approved`; `finance_status='finance_ok'` | `returned_finance + is_void_return=True`. |
| Can finance confirm void? | `status='returned_finance'` AND `is_void_return=True` | Single-step: auto-reverses finance reg if needed; `status='void_confirmed'`. |
| Can commercial request admin review? | From `temp_commercial`, `approved`, `incomplete`, `rejected` | `needs_admin_review=True`. |
| Can superuser admin-edit? | `is_superuser=True` | Full edit form; full before/after log; `is_admin_edited=True`. |
| Can finance return to commercial? | Finance user; record not locked/rejected | `status='returned_commercial'`. |
| Can staff operate incomplete record? | `status='incomplete'` | No; only customer correction continues flow. |
| Can staff operate rejected record? | `status='rejected'` | No; locked; history-only. |
| Can counterparty see record? | `payment.counterparty` matches linked counterparty user | Appears in counterparty dashboard. |
| Should dashboard show record? | Current state requires action from current department | Show in dashboard. |
| Should history show record? | User authorized by role/ownership | Show regardless of status. |

## Notification Color Table

| Event | Recipients | Color |
| --- | --- | --- |
| Customer upload | staff | `#DDF6D2` |
| Finance registration | commercial | `#DDF6D2` |
| Commercial registration | finance | `#B5F1CC` |
| Temp commercial registration | finance (only if finance_ok) | `#FEEAC9` |
| Counterparty approval | commercial | `#B5F1CC` |
| Counterparty return | commercial | `#FEEAC9` |
| Counterparty rejection | commercial | `#FECACA` |
| Payment rejection | commercial + customer | `#FECACA` |
| Return to commercial | commercial | `#E9D5FF` |
| Void return to finance | finance | `#DBEAFE` |
| Void confirmed | commercial + customer | `#FECACA` |
| Admin review request | superuser | `#FEF3C7` |
| Admin edit | commercial + finance | `#FEF3C7` |

## Customer Display Rules

```mermaid
flowchart LR
    A[Internal payment status] --> B{Actionable by customer?}
    B -- incomplete --> C[Show: Incomplete<br/>customer must correct]
    B -- rejected --> D[Show: Rejected]
    B -- approved --> E[Show: Commercial registered]
    B -- final_approved --> F[Show: Final approved]
    B -- void_confirmed --> G[Show: Voided]
    B -- is_admin_edited log --> H[Show: Details changed...]
    B -- all other internal states --> I[Show: Under review]
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
    F --> J{status void_confirmed / rejected / final_approved?}
    J -- Yes --> I
    F --> K{status incomplete?}
    K -- Yes --> L[Hide from staff dashboard<br/>customer correction required]
    F --> M{needs_admin_review=True?}
    M -- Yes --> N[Show in Admin Review Queue for superuser]
    F --> O{status = returned_finance + is_void_return?}
    O -- Yes --> P[Show in Voided Documents dashboard for finance]
    F --> Q{status = temp_commercial?}
    Q -- Yes --> R[Show in In Progress dashboard for commercial]
```
