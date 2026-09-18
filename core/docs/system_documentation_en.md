# Customer Management System Documentation

Last updated: 2026-09-18  
Code reference: `payments/models.py`, `payments/views.py`, `payments/forms.py`, `payments/urls.py`  
Related workflow chart: `docs/payment_receipt_workflow_flowchart.md`

## 1. Purpose

This Django application manages the operational relationship between customers, finance staff, commercial staff, sales staff, warranty staff, managers, and counterparties. Its central workflow is the customer payment receipt lifecycle, but the system also includes daily payment plans, daily payment notices, invoices, price lists, customer orders, proformas, reconciliation conversations, customer access management, counterparties, warranty claims, agency applications, SMS/MFA support, exports, desktop UI, and mobile/PWA UI.

The main product rules are:

- Customers can use the web portal or mobile/PWA UI to upload receipts and view their own documents.
- Finance, commercial, and sales users can work on the same customer payment record according to their role.
- Operational dashboards should show records that need action. Completed records should move to history.
- Every important state transition should create a history log and a notification.
- File previews and downloads must work consistently for images and PDFs in both desktop and mobile contexts.
- The system must respect role-based access, customer ownership, assigned sales ownership, and counterparty ownership.

## 2. Roles

Roles are stored mainly in `UserProfile.role`; Django `is_staff` and `is_superuser` are also considered.

| Role | Meaning |
| --- | --- |
| `customer` | Customer portal user. Can manage own receipts, orders, invoices, price lists, notices, profile, warranty claims, and allowed reconciliation threads. |
| `counterparty` | Counterparty user. Can see payment records assigned to its `Counterparty` record and approve/return/reject them. |
| `finance` | Finance staff. Can register finance actions and return records to commercial when needed. |
| `finance_manager` | Finance manager. Has broader finance access, final approval/delegation access, and may import accounting codes when the feature is enabled. |
| `commercial` | Commercial staff. Can register commercial review, temporary registration, void return to finance, reject, mark incomplete, request admin review, and assign counterparties. |
| `commercial_manager` | Commercial manager. Has broader commercial access and may import accounting codes when the feature is enabled. |
| `sales` | Sales staff. Can view assigned customers, assigned customer documents, orders, and daily payment expectations. |
| `sales_manager` | Sales manager. Can manage sales assignments and broader sales workflows. |
| `data_entry` | Staff role for completing receipt details. |
| `staff` | Generic staff role. |
| `warranty` | Warranty staff. |
| `warranty_manager` | Warranty manager. |
| `superuser` | Full administrative access. |

General role decisions:

- A user is treated as staff if `is_staff=True`, `is_superuser=True`, or the profile role is one of the staff roles.
- `superuser` bypasses most business restrictions.
- A normal `sales` user is limited to customers assigned through `CustomerSalesAssignment`.
- A customer can only access their own records.
- A counterparty can only access payment records assigned to its counterparty record.
- Department managers can manage access only for users in their own department. `superuser` can manage all non-customer staff users.

## 3. Core Data Model

### User and Profile

`UserProfile` extends Django `User` with:

- first name, last name, phone, mobile, second mobile
- representative contact fields
- organization, province, city, addresses
- role
- active-from and valid-until dates
- forced password change flag
- suspension flag
- invoice permissions
- payment details edit permission
- reconciliation access flag
- accounting code
- avatar configuration

Important behavior:

- Suspended or inactive users should not be able to perform normal operations.
- Customer-facing labels should prefer full name and organization over raw username.
- Sales users see only assigned customers in customer-limited workflows.

### System Settings

`SystemSettings` stores singleton application settings, including:

- system logo and menu settings
- SMS provider configuration
- OTP/MFA behavior
- session timeout and multiple-session policy
- customer warranty menu toggle
- accounting-code import toggle
- Jitsi/video-call settings

### Upload Settings

`UploadSettings` stores max upload size for:

- receipt files
- invoice files

Forms should use these limits when validating uploaded files.

### Field Requirement Configuration

`FieldRequirementConfig` allows admin-level overrides for required fields.

Decision rule:

- `is_required=None`: use the code default.
- `is_required=True`: force the field to be required.
- `is_required=False`: force the field to be optional.

Covered forms:

- payment receipt form
- staff payment details form
- order form
- order item form
- customer profile form
- proforma form
- counterparty form
- counterparty bank account form

Implementation note:

- Required-field configuration is cached for 60 seconds.
- UI must show required fields with a red star.
- Staff forms must not accidentally require fields that were not configured as required.

## 4. Payment Receipt Workflow

Primary model: `PaymentRecord`  
Attachment model: `PaymentReceipt`  
History model: `PaymentActivityLog`

### 4.1 Customer Upload

When a customer uploads a receipt:

- The payment record is created or updated.
- Main status becomes `pending` / "Under review".
- Finance flag remains `None`, which means "waiting for finance registration".
- Receipt files are stored through secure unique upload paths.
- A payment history entry is created.
- Internal staff notifications are created.
- Notification color for initial receipt upload is `#DDF6D2`.
- SMS support exists in the system, but actual sending depends on SMS settings.

Recommended SMS content should stay short:

```text
Receipt received.
Amount: ... IRR
Tracking: ...
Status: Under review
```

### 4.2 Payment Main Statuses

| Code | Label | Business meaning |
| --- | --- | --- |
| `pending` | Under review | Customer submitted the receipt. Staff action is needed. |
| `commercial_review` | Commercial review | Record enters commercial review automatically on creation. |
| `temp_commercial` | Temporary commercial registration | Commercial has entered a temporary/non-final state. Record appears in the "In Progress" commercial dashboard. |
| `approved` | Commercial registered | Commercial registration is done. |
| `final_approved` | Final approved | Final approval is complete. |
| `rejected` | Rejected | Record is locked for everyone — including the staff member who rejected it — and removed from operational flow. Stays visible (read-only) in the finance dashboard until finance confirms the rejection (`rejection_confirmed_at`). |
| `incomplete` | Incomplete | Company staff cannot operate; customer must correct the record based on staff note. Visible (read-only) in the finance dashboard the moment commercial marks it incomplete. |
| `returned_commercial` | Returned to commercial | Finance returned the record to commercial. |
| `returned_finance` | Returned to finance | Commercial returned the record to finance. If `is_void_return=True`, this is a void request. |
| `void_confirmed` | Voided | Void is confirmed by finance. Record exits all operational dashboards. |

> **Removed**: `follow_up` status has been fully removed. Cases requiring additional investigation are handled via the "Return to Admin Queue" action.

### 4.2.1 Admin Edit Flags

Two additional boolean fields on `PaymentRecord` manage superuser editing:

| Field | Type | Meaning |
| --- | --- | --- |
| `needs_admin_review` | BooleanField | Record is in the admin review queue. |
| `is_admin_edited` | BooleanField | Record was edited by a superuser. Table rows show a small orange triangle in the corner. |
| `admin_edited_at` | DateTimeField | Timestamp of the last admin edit. |
| `admin_edited_by` | ForeignKey | The superuser who edited the record. |

### 4.2.2 Void Flags

| Field | Type | Meaning |
| --- | --- | --- |
| `is_void_return` | BooleanField | This `returned_finance` is a void request, not a regular return. |
| `void_reason` | TextField | Void reason entered by commercial. |

### 4.2.3 Rejection Confirmation Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `rejection_confirmed_at` | DateTimeField | When finance confirmed the rejection. While `None`, the record stays in the finance dashboard. |
| `rejection_confirmed_by` | ForeignKey | The finance user who confirmed the rejection. |

### 4.2.4 Regular-Return Confirmation Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `return_confirmed_at` | DateTimeField | When finance confirmed a regular (non-void) return. While `None`, the record stays in the finance dashboard regardless of `finance_status`. |
| `return_confirmed_by` | ForeignKey | The finance user who confirmed the return. |

### 4.3 Finance Flag

Finance registration is independent from the commercial status.

| Value | Meaning |
| --- | --- |
| `None` | Waiting for finance registration |
| `finance_ok` | Finance registered |

When finance registers a receipt:

- `finance_status='finance_ok'`
- `finance_registered_at` is set.
- `finance_registered_by` is set.
- A history log is created.
- A notification is created with color `#DDF6D2`.
- The record should leave the finance operational dashboard unless another state requires action.

### 4.4 Commercial Actions

Commercial staff can act on a receipt while finance can also act independently.

#### From "Commercial Review" state

| Action | Result | Notification color |
| --- | --- | --- |
| Temporary commercial registration | `temp_commercial` | `#FEEAC9` |
| Commercial registration | `approved` | `#B5F1CC` |
| Mark incomplete | `incomplete` | `#FEF3C7` |
| Reject | `rejected` | `#FECACA` |
| Request admin review | `needs_admin_review=True` | `#FEF3C7` |

> From this point on, "incomplete" and "reject" always notify commercial + finance + customer unconditionally, and both are also visible (read-only) in the finance dashboard — no prior finance registration is required.

#### From "Temporary commercial registration" (`temp_commercial`)

Record is visible in the "In Progress" commercial dashboard. Finance can also see it if `finance_status == finance_ok`.

| Action | Condition | Result |
| --- | --- | --- |
| Commercial registration | — | `approved` |
| Void return to finance | `finance_status == finance_ok` | `returned_finance + is_void_return=True` |
| Mark incomplete | — | `incomplete`; always notifies commercial + finance + customer; shown read-only in finance dashboard |
| Reject | — | `rejected`; locked for everyone; always notifies commercial + finance + customer; shown in finance dashboard until confirmed |
| Request admin review | — | `needs_admin_review=True` |

#### From "Commercial registered" (`approved`)

| Action | Condition | Result |
| --- | --- | --- |
| Temporary commercial registration | — | `temp_commercial`; finance notified if registered |
| Void return to finance | `finance_status == finance_ok` | `returned_finance + is_void_return=True` |
| Mark incomplete | — | `incomplete`; always notifies commercial + finance + customer; shown read-only in finance dashboard |
| Reject | — | `rejected`; locked for everyone; always notifies commercial + finance + customer; shown in finance dashboard until confirmed |
| Request admin review | — | `needs_admin_review=True` |

> **Rule for "Return to Finance"**: This action is exclusively for voiding a payment. It is irreversible except by a superuser. Condition: `finance_status == finance_ok`.

Every commercial action must:

- validate user permission
- validate state transition
- save staff notes when applicable
- create `PaymentActivityLog`
- create relevant `UserNotification`
- keep history available to all authorized users

### 4.4.1 Void Workflow

```
Commercial (from temp_commercial or approved, requires finance_ok)
  → Return to finance (is_void_return=True)
Finance — Voided Documents dashboard
  → Confirm void (single step)
    - If finance_status == finance_ok: finance registration is reversed automatically
    - status = void_confirmed
    - Notify commercial + customer (color #FECACA)
```

### 4.4.2 Admin Review Queue Workflow

```
Commercial (from temp_commercial, approved, incomplete, or rejected)
  → Request admin review
    → needs_admin_review=True
    → Notify superuser (color #FEF3C7)
Superuser — Admin Review Queue dashboard
  → Open full edit form for the record
    - All changes logged with before/after values
    - Customers see only "Details changed..." in history
    - is_admin_edited=True, needs_admin_review=False
    - Notify commercial + finance (color #FEF3C7)
    - Record row shows a small orange triangle in table corners
```

### 4.4.3 Rejection & Finance Confirmation Workflow

```
Commercial (or any department) rejects the record
  → rejection_reason is required (free-text note also required when reason = "other")
    - status = rejected
    - is_locked = True for everyone — no role (except via the separate admin review queue) can
      change the status again, not even the staff member who rejected it
    - Notify commercial + finance + customer unconditionally (color #FECACA)
    - Record is immediately visible in the finance dashboard, read-only (no action buttons)
Finance — main dashboard (rejected row)
  → Confirm rejection (single step, via the same finance action form — "Confirm rejection" option)
    - If finance_status == finance_ok: finance registration is reversed automatically
      and logged as ACTION_FINANCE_REJECTION_REVERSED
    - rejection_confirmed_at / rejection_confirmed_by are set
    - ACTION_REJECTION_CONFIRMED is logged; commercial + sales are notified (color #FECACA)
    - Record leaves the finance active queue; still fully visible in history/timeline
```

### 4.4.4 Incomplete & Customer Edit Workflow

```
Commercial marks the record incomplete (a note is required)
  → status = incomplete
    - Staff operations are blocked; only the customer can correct the record
    - Notify commercial + finance + customer unconditionally (color #FEF3C7)
    - Record is immediately visible in the finance dashboard, read-only (no action buttons)
Customer submits the edit form
  → Before applying changes, the current value of every editable field (payer name/account,
    beneficiary bank/account/owner, amount, tracking code, date, notes, counterparty, receipt file)
    is captured
    - After saving, every changed field is logged as `field: «before» → «after»` on the
      ACTION_EDITED log entry
    - status = pending (the same starting point as a brand-new upload — commercial's dashboard
      auto-flips it to commercial_review once viewed)
    - Any prior finance registration is cleared so finance re-checks the record
    - Prior history/logs are never deleted; the full timeline remains visible
```

### 4.4.5 Regular Return & Finance Confirmation Workflow

A regular return ("Return to finance" from commercial's dropdown, distinct from the void path) is available from any active commercial state, regardless of whether finance has already registered.

```
Commercial returns the record to finance
  → status = returned_finance, is_void_return=False
    - finance_status is left untouched
    - Notify commercial + finance + sales (color #DBEAFE)
    - Record is immediately visible in the finance dashboard regardless of finance_status
      (before this fix, if finance had already registered, the record would never appear
      in the finance dashboard at all)
Finance — main dashboard (returned row)
  → Confirm return (single step, via the "Confirm return" option in the finance action form)
    - return_confirmed_at / return_confirmed_by are set
    - finance_status is NOT changed — this confirmation only records that finance updated
      their own external accounting system, independent of the in-app "finance registered" flag
    - Notify commercial + sales (color #DBEAFE)
    - Record leaves the finance active queue; still fully visible in history/timeline
```

### 4.5 Finance Actions

Finance staff can:

- register finance
- return to commercial
- participate in final approval workflows
- view history and records according to role

Return to commercial:

- status becomes `returned_commercial`
- notification color `#E9D5FF`
- record must return to commercial dashboard
- commercial staff must be able to see the new flag/state

### 4.6 Counterparty Actions

Commercial can assign a payment record to a counterparty.

Counterparty behavior:

- The assigned payment appears in the counterparty dashboard.
- If the counterparty is active, it can operate.
- If the counterparty is inactive, login may be allowed but operations are not allowed.
- If the counterparty is suspended, login is disabled through the linked user.

Counterparty decisions:

| Decision | Effect |
| --- | --- |
| Approve | Counterparty confirms that the payment matches the receipt. Notification color `#B5F1CC`. |
| Return | Counterparty asks for more review or returns the item. Notification color `#FEEAC9`. |
| Reject | Counterparty rejects the payment and provides a reason. Notification color `#FECACA`. |

If a counterparty rejects or returns the receipt, commercial should usually move it to `follow_up` and ask the customer for a statement or additional evidence.

### 4.7 Customer-Visible Status Mapping

Many internal states are intentionally simplified for customers.

| Internal status | Customer sees |
| --- | --- |
| `pending`, `commercial_review`, `temp_commercial`, `returned_commercial`, `returned_finance` | Under review |
| `approved` | Commercial registered |
| `final_approved` | Final approved |
| `rejected` | Rejected |
| `incomplete` | Incomplete |
| `void_confirmed` | Voided |

Admin edits (`is_admin_edited=True`): customers see only "Details changed..." in history — no field-level details are exposed.

### 4.8 Dashboards vs History

Available dashboards:

| Dashboard | URL | Access | Content |
| --- | --- | --- | --- |
| Main work queue | `submit/` | All staff | Records requiring action |
| In Progress (commercial) | `commercial/temp/` | Commercial | Records with `temp_commercial` status |
| Voided Documents | `finance/voided/` | Finance | Records with `returned_finance + is_void_return=True` |
| Admin Review Queue | `admin/review-queue/` | Superuser only | Records with `needs_admin_review=True` |
| Pending Final Approval | `finance/pending-final-approval/` | Finance manager | Records ready for final approval |
| History | `payments/history/` | All staff | All authorized records, any status |

Business rules:

- Dashboards show items that need action.
- History shows all authorized records regardless of status.
- `void_confirmed` and `final_approved` records are excluded from operational dashboards.
- `incomplete` records and unconfirmed `rejected` records (`rejection_confirmed_at=None`) are excluded from the commercial dashboard, but remain visible read-only (no action buttons) in the finance dashboard — rejected until finance confirms, incomplete until the customer corrects it.
- Unconfirmed regular `returned_finance` records (`is_void_return=False`, `return_confirmed_at=None`) are visible in the finance dashboard **regardless of `finance_status`** — this closed a bug where the record would disappear from the finance dashboard entirely if finance had already registered it.
- Returned records must re-appear in the relevant department's dashboard.
- History must show all records regardless of status.

## 5. Notifications

Model: `UserNotification`

Fields include:

- user
- title/message
- URL
- category
- color
- `is_read`
- `read_at`
- timestamps

Expected behavior:

- Every important event creates a notification for relevant users.
- Unread count is based on `is_read=False`.
- Opening `notifications/<id>/open/` should mark that notification read and redirect to its target URL.
- Calling `api/notifications/read/` marks notifications read in bulk.
- Counts must decrease after a notification is read.

Reference colors:

| Event | Color |
| --- | --- |
| Customer receipt upload | `#DDF6D2` |
| Finance registration | `#DDF6D2` |
| Commercial registration | `#B5F1CC` |
| Temporary commercial registration (when finance registered) | `#FEEAC9` |
| Counterparty approval | `#B5F1CC` |
| Counterparty return | `#FEEAC9` |
| Counterparty rejection | `#FECACA` |
| Marked incomplete (commercial + finance + customer, unconditional) | `#FEF3C7` |
| Payment rejection (commercial + finance + customer, unconditional) | `#FECACA` |
| Rejection confirmed by finance (commercial + sales get) | `#FECACA` |
| Return to commercial (commercial + sales get) | `#E9D5FF` |
| Return to finance — regular (commercial + finance + sales get) | `#DBEAFE` |
| Void return to finance (finance gets) | `#DBEAFE` |
| Regular return confirmed by finance (commercial + sales get) | `#DBEAFE` |
| Void confirmed (commercial + customer get) | `#FECACA` |
| Admin review request (superuser gets) | `#FEF3C7` |
| Admin edit (commercial + finance + sales + customer get) | `#FEF3C7` |

### Categories and tabbed display

`UserNotification.category` has seven values:

| Value | Label | Covers |
| --- | --- | --- |
| `payment` | Payment receipt | All payment-receipt workflow events (creation, status changes, final approval, return, void, admin edit, counterparty decisions) |
| `invoice` | Invoice & sales documents | Invoices, price lists, proformas (issuance and approval) |
| `order` | Order | Order creation, status changes, sales-expert assignment, proforma issued for an order |
| `warranty` | Warranty | All warranty-claim workflow events |
| `agency` | Agency | Agency application submission and approval/rejection |
| `reconciliation` | Reconciliation | New message in a reconciliation thread |
| `system` | System | Management actions not tied to one specific document — sales-customer assignment/transfer, final-approval delegation |

> Previously everything except payment/invoice fell under one generic "system" bucket. This split was introduced specifically to enable tabbed filtering.

**Tabbed notification dropdown**: if a user's unread notifications span more than one category, a tab bar ("All" + the categories present) appears above the list; clicking a tab filters client-side (over the already-fetched batch — no extra server round-trip). If all of a user's unread notifications share one category, the tab bar is not shown at all.

## 6. File Handling

Server-side file names:

- must be unique
- must be safe
- must not depend on customer-facing display text
- are generated through upload helpers using folder, model name, actor id, timestamp, and UUID token

Download file names:

- should be user-friendly
- should preserve the original file extension
- should use the same rule for images and PDFs
- for payment receipt downloads, should include existing document metadata plus destination account owner name
- should separate name parts with `-`
- should not rename files stored on the server

PDF preview:

- must display the document itself without the side navigation panel
- should use browser PDF controls for scrolling and zooming
- expected URL fragment:

```text
#toolbar=1&navpanes=0&scrollbar=1&view=FitH
```

Access rule:

- A user who cannot access a document must not preview or download its file.

### Receipt File Versioning

When a customer replaces the receipt image/PDF (correcting an `incomplete` record), the previous file is **not deleted**:

- `PaymentReceipt.is_current` (default `True`) marks the active file(s); the previous one(s) are flipped to `is_current=False` with `replaced_at` set.
- The unique-hash constraint (`payment` + `file_hash`) is scoped to `is_current=True` only, so a customer can legitimately re-upload a file matching a now-superseded version without a false "duplicate file" error.
- Customer-facing pages only ever show `payment.current_receipts`.
- Staff-facing pages (main dashboard, payment timeline, staff customer-detail view) additionally show a "Previous versions" section (`payment.superseded_receipts`) so commercial/finance can compare the image before vs. after the customer's edit.

## 7. Daily Payment Plans and Notices

Models:

- `DailyPaymentPlan`
- `DailyPaymentAssignment`
- `DailyPaymentNotice`

Purpose:

- Staff define planned payments by date and destination account.
- Customers are assigned to plans with expected amounts.
- Sales users can see expected collection amounts for their assigned customers.
- Staff can generate a daily notice showing receipt count and total receipt amount for a specific customer/date.

Rules:

- Default date for notice generation should be yesterday.
- Staff can edit the generated notice text before publishing.
- For the same customer and date, duplicate publishing should show a warning.
- If staff confirms the duplicate, the previous notice is updated and shown again to the customer.
- Customer splash/highlight should be attention-grabbing but should show only once per login/session.
- Returning to dashboard or refreshing should not keep showing the same splash repeatedly after it is marked seen.
- Staff and customer should both have table-based history views for notices.

## 8. Customers and Accounting Codes

Customers may have accounting detail codes stored on `UserProfile.accounting_code`.

Excel import route:

- `customers/import-accounting-codes/`

Conditions:

- `SystemSettings.accounting_code_import_enabled` must be enabled.
- allowed roles: `superuser`, `finance_manager`, `commercial_manager`

Import decisions:

- Excel customer data may not exactly match database customer data.
- Import should use preview, matching, validation, and warning rows.
- Ambiguous matches should not be blindly written.
- Final database update should be auditable.

Customer lists should display more than username:

- full name
- organization
- city and province
- phone/mobile
- accounting code
- status
- assigned sales user when relevant

## 9. Invoices

Models:

- `InvoiceRecord`
- `InvoiceExtractionJob`

Features:

- upload invoices
- parse/preview invoice extraction
- view invoice detail
- download invoice file
- delete invoice by authorized user
- customer note and seen status

Access:

- Customers see their own invoices.
- Staff access depends on invoice view/upload permissions and role.
- Normal sales users are limited to assigned customers.

## 10. Price Lists

Model: `PriceList`

Features:

- upload public or customer-specific price lists
- customer download/view
- delete by authorized staff
- track customer seen time

Upload access:

- `superuser`
- commercial/commercial manager
- sales/sales manager
- finance/finance manager

## 11. Orders and Proformas

Models:

- `CustomerOrder`
- `CustomerOrderItem`
- `CustomerOrderLog`
- `ProformaInvoice`
- `ProformaInvoiceLog`
- `ProductCatalog`

Order statuses:

| Code | Meaning |
| --- | --- |
| `submitted` | Customer submitted order. |
| `reviewing` | Staff is reviewing. |
| `proforma_sent` | Proforma was sent. |
| `completed` | Order completed. |
| `cancelled` | Order cancelled. |

Rules:

- Customers can submit orders.
- Sales/commercial users can review and update orders.
- Proformas can be issued by authorized sales/commercial users.
- Customers can view and approve proformas.
- History logs must be created for important order/proforma changes.

## 12. Reconciliation Conversations

Models:

- `ReconciliationThread`
- `ReconciliationMessage`
- `ReconciliationMessageLog`
- `ReconciliationMessageReadReceipt`
- `ReconciliationReadState`
- `ReconciliationThreadPin`

Document types:

- payment
- order
- proforma
- invoice
- daily payment
- other

Rules:

- Staff and customers can access reconciliation if permitted by role/settings.
- Customers see only their own non-internal threads.
- Internal threads are staff-only.
- Messages can include text, attachment, and document reference.
- Attachments block executable/script/installer-like extensions.
- Max reconciliation attachment size is 10 MB.
- Thread unread count is based on messages from others created after the user's last read state.
- Opening/reading a thread should update read state and decrease unread count.

## 13. Warranty

Models:

- `WarrantyClaim`
- `WarrantyClaimFile`
- `WarrantyClaimLog`

Statuses:

| Code | Meaning |
| --- | --- |
| `submitted` | Claim submitted. |
| `reviewing` | Under review. |
| `info_needed` | Customer must provide more information. |
| `approved` | Warranty approved. |
| `in_progress` | Processing/repair in progress. |
| `resolved` | Resolved. |
| `rejected` | Rejected. |
| `closed` | Closed. |

Priorities:

- low
- normal
- high
- urgent

Resolution types:

- repair
- replace
- refund

Rules:

- Customer, agent, or staff can submit warranty claims.
- A tracking code is generated.
- Files can be attached.
- Warranty staff can start review, request info, approve, move to in-progress, resolve, reject, close, assign, change priority, add notes, and add files.
- Customer can reply only when status is `info_needed`.
- Customer can rate after resolved/closed.
- Logs may be visible or hidden from customer.

## 14. Agency Applications

Models:

- `AgencyApplication`
- `AgencyApplicationLog`

Public flow:

- phone entry
- phone verification
- application form
- tracking code
- status tracking

Statuses:

| Code | Meaning |
| --- | --- |
| `pending` | Waiting for review. |
| `reviewing` | Under review. |
| `info_needed` | More information required. |
| `approved` | Approved. |
| `rejected` | Rejected. |

Sales staff/managers can review agency applications. Approval may create a linked user account.

## 15. SMS, OTP, and MFA

Models:

- `SMSOTPCode`
- `SMSSendLog`

Capabilities:

- SMS provider configuration
- OTP verification
- SMS MFA setup
- test SMS sending
- operational SMS hooks

Decision:

- SMS infrastructure exists but may be disabled.
- Disabled or misconfigured SMS should not block the main business operation unless the specific feature requires OTP verification.
- Operational SMS messages should remain short.

## 16. User and Access Management

Features:

- user list
- user edit
- business card
- password reset
- access management
- role and permission flag editing

Rules:

- Full user management is `superuser`-only.
- Department managers can manage access for their department users only.
- Customers and counterparties are excluded from staff access management.
- Suspended/inactive users should not be able to operate.

## 17. Counterparties

Models:

- `Counterparty`
- `CounterpartyBankAccount`

Counterparty statuses:

| Code | Meaning |
| --- | --- |
| `active` | Login and operations allowed. |
| `inactive` | Login allowed; operations disabled. |
| `suspended` | Login disabled. |

Rules:

- Suspending a counterparty disables its linked user account.
- A counterparty can have multiple bank accounts.
- Only one bank account can be primary.
- Counterparty bank accounts support destination account selection and receipt review.

## 18. Desktop and Mobile UI

Design rules:

- Main font should be Vazir across the application.
- UI direction is RTL.
- Desktop uses a right-side sidebar and top header.
- Mobile/PWA uses bottom navigation and hamburger/off-canvas menu.
- Logout must be available in the mobile hamburger menu and desktop sidebar.
- Desktop top logout can be hidden if sidebar logout exists.
- Menu captions must have readable contrast.
- Header brand/logo and "Customer Management System" title are placed on the right; user/message/notification controls are on the left.
- Cards must not force horizontal scrolling.
- Tables should become readable card/list layouts on mobile.
- Required fields must show a red star.
- Origin account and destination account groups should be visually separated.

PWA details:

- manifest route: `manifest.json`
- service worker route: `sw.js`
- current cache name in code: `rabasa-customer-pwa-v17`
- current static busting token: `ui-redesign-v17`

## 19. Main URL Map

Customer/payment:

- `submit/`
- `submit/new/`
- `success/`
- `payments/<id>/timeline/`
- `payments/history/`
- `receipts/<id>/file/`
- `receipts/<id>/rotate/`

Notifications:

- `api/notifications/`
- `api/notifications/read/`
- `notifications/<id>/open/`

Customers/daily payment:

- `customers/`
- `customer/<id>/`
- `customers/import-accounting-codes/`
- `daily-payments/`
- `daily-payments/<id>/`
- `daily-payment-notices/`
- `daily-payment-notices/<id>/seen/`

Finance/final approval:

- `payments/<id>/finance-register/`
- `payments/<id>/finance-action/`
- `payments/<id>/final-approve/`
- `payments/<id>/void/` — void return to finance (commercial action)
- `payments/<id>/void-confirm/` — confirm void (finance action)
- `finance/pending-final-approval/`
- `finance/delegation/`
- `finance/bulk-approve/`
- `finance/voided/` — voided documents dashboard

Commercial/status:

- `payments/<id>/status/`
- `payments/<id>/details-edit/`
- `payments/<id>/edit/`
- `payments/<id>/note/`
- `payments/<id>/request-admin-review/` — send to admin review queue
- `commercial/temp/` — "In Progress" commercial dashboard

Admin:

- `admin/review-queue/` — admin review queue (superuser only)
- `admin/payments/<id>/edit/` — full edit form for superuser

Reconciliation:

- `finance/reconciliation/`
- `finance/reconciliation/poll/`
- `finance/reconciliation/start-thread/`
- `finance/reconciliation/attachments/<message_id>/`
- `api/reconciliation-messages/`
- `call/`

Invoices/price lists/orders/proformas:

- `invoices/`
- `invoices/parse-preview/`
- `invoices/<id>/`
- `invoices/<id>/file/`
- `price-lists/`
- `price-lists/<id>/file/`
- `orders/`
- `orders/<id>/`
- `proformas/`
- `proformas/<id>/`
- `proformas/<id>/file/`

Counterparty:

- `counterparty/`
- `counterparty/payments/<id>/approve/`
- `counterparty/payments/<id>/return-cp/`
- `counterparty/payments/<id>/reject-cp/`
- `counterparties/`
- `counterparties/manage/`

Warranty:

- `warranty/`
- `warranty/my/`
- `warranty/track/`
- `warranty/<id>/`
- `warranty/staff/`
- `warranty/staff/<id>/`

Agency:

- `agency/`
- `agency/verify/`
- `agency/apply/`
- `agency/track/`
- `sales/agency/`

Admin/tools:

- `users/`
- `access-management/`
- `export-records/`
- `export/<dataset>/`
- `admin-tools/receipt-reader/`
- `admin-tools/system-logo/`
- `sms-verify/`
- `sms-mfa/setup/`
- `profile/`

## 20. Logs and Audit Trail

Important log models:

- `PaymentActivityLog`
- `SystemActivityLog`
- `CustomerOrderLog`
- `ProformaInvoiceLog`
- `ReconciliationMessageLog`
- `WarrantyClaimLog`
- `AgencyApplicationLog`
- `SMSSendLog`
- `LoginRecord`

Rules:

- Important status changes must be logged.
- Logs should store actor, timestamp, action, and note.
- Customer-visible logs must explicitly mark visibility.
- Staff-only internal notes must not leak into customer views.

## 21. Development and Maintenance Decisions

Keep these rules when modifying the system:

- Finance flag is independent from commercial status.
- Finance and commercial can act on the same payment record independently.
- **"Return to finance" has two independent paths**: **regular** (from any active commercial state, unconditional on finance registration — requires finance to confirm via `return_confirmed_at`, finance_status stays untouched) and **void** (`is_void_return=True`, only from `temp_commercial`/`approved`, condition `finance_status == finance_ok`, irreversible except by superuser).
- **`follow_up` status is removed**: do not re-add it. Use the admin review queue instead.
- **Void flow**: commercial sets `returned_finance + is_void_return=True`; finance confirms in one step; finance registration is auto-reversed if needed; status becomes `void_confirmed`.
- **`is_void_return` flag**: never reset when setting `returned_finance` — it distinguishes void return from regular return.
- **`void_confirmed`** exits all operational dashboards permanently.
- **`needs_admin_review`**: set to `False` after admin edits, not before.
- **`is_admin_edited`**: drives the orange triangle CSS indicator in table rows.
- **Admin edit logging**: log all field values before and after. Customers see only "Details changed..." — never field names or values.
- Finance notification for `temp_commercial` transitions: only send when `finance_status == finance_ok`.
- Finance notification for `incomplete` and `rejected` transitions: always sent, unconditionally — both are now always visible in the finance dashboard too.
- Return-to-commercial should move the record back to the commercial operational dashboard.
- Rejected records are locked out of operational flow for everyone, including the staff member who rejected them. They stay visible (read-only) in the finance dashboard until finance confirms the rejection (`rejection_confirmed_at`), which auto-reverses any prior finance registration.
- Incomplete records pause staff operations and require customer correction; they're visible (read-only) in the finance dashboard the moment they're marked incomplete.
- A customer's fix on an incomplete record resets status to `pending` (same starting point as a new upload) and logs every changed field as `field: «before» → «after»` on the edit's activity log; prior history is never deleted.
- A regular (non-void) return to finance must be visible in the finance dashboard regardless of `finance_status`, and only leaves the queue once `return_confirmed_at` is set — finance_status is never touched by that confirmation.
- A customer's replaced receipt file/image is never physically deleted — only flipped to `is_current=False` so staff can compare the before/after version.
- History must show all authorized records with all statuses.
- Notifications must have color, category, unread/read behavior, and URL navigation.
- File download names must be consistent for image and PDF.
- Mobile UI changes must not break desktop UI.
- Model changes require migration creation and execution.
- Static/CSS/JS changes may require cache-busting and `collectstatic`.

## 22. Test Scenarios

Payment receipt:

1. Customer uploads image receipt.
2. Customer uploads PDF receipt.
3. Customer enters tracking code that contains non-numeric characters.
4. Commercial registers the payment (approved).
5. Commercial marks temporary registration (temp_commercial) — record appears in "In Progress" dashboard.
6. Commercial marks incomplete — record is immediately visible (read-only) in the finance dashboard and notifies commercial + finance + customer.
7. Customer edits and resubmits the incomplete record — every changed field is logged as "before → after"; status resets to `pending`.
8. Commercial rejects — a rejection reason is required, the record locks for everyone, and it's immediately visible in the finance dashboard.
9. Finance confirms the rejection — any prior finance registration is auto-reversed; `rejection_confirmed_at/by` are set; record leaves the finance active queue.
10. Finance registers payment.
11. Finance returns to commercial.
12. Commercial returns to finance (regular, not void) — record must be immediately visible in the finance dashboard even if finance had already registered it.
13. Finance confirms the regular return — `return_confirmed_at/by` set, `finance_status` unchanged, record leaves the finance active queue.
14. Commercial (from temp_commercial) voids the payment — requires finance_ok.
15. Commercial (from approved) voids the payment — requires finance_ok.
16. Finance confirms void — finance registration auto-reversed; status = void_confirmed.
17. Counterparty approves.
18. Counterparty returns or rejects.
19. Commercial requests admin review (from any of: temp_commercial, approved, incomplete, rejected).
20. Superuser opens admin review queue, edits record with full before/after log.
21. Confirm is_admin_edited=True; row shows orange triangle; commercial and finance notified.
22. Customer replaces the receipt image on an incomplete record — previous file must not be deleted; staff should see it under "Previous versions"; customer should only see the current one.
23. Each step updates history and notifications correctly.

Notification:

1. Create unread notification.
2. Confirm unread count increases.
3. Click notification.
4. Confirm target opens.
5. Confirm notification becomes read.
6. Confirm count decreases.
7. Test bulk mark-read endpoint.

Files:

1. Preview JPG on desktop.
2. Preview JPG on mobile.
3. Preview PDF on desktop.
4. Preview PDF on mobile.
5. Download JPG with standard name.
6. Download PDF with standard name.
7. Confirm unauthorized user cannot access file.

Mobile/desktop UI:

1. Customer dashboard has no horizontal scrolling on mobile.
2. Staff dashboard cards are readable on mobile.
3. Hamburger menu includes logout.
4. Desktop sidebar captions are readable.
5. Customer list actions are accessible without annoying horizontal scroll.
6. Forms show only configured required fields.

Daily notices:

1. Default date is yesterday.
2. Generate customer/day notice.
3. Duplicate customer/day publish warns staff.
4. Confirming duplicate updates previous notice.
5. Customer sees splash once.
6. Notice histories are visible in tables.

