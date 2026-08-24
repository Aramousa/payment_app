# Customer Management System Documentation

Last updated: 2026-08-24  
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
| `commercial` | Commercial staff. Can register commercial review, temporary registration, return to finance, reject, mark incomplete, follow up, and assign counterparties. |
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
| `commercial_review` | Commercial review | Commercial review is in progress. |
| `temp_commercial` | Temporary commercial registration | Commercial has entered a temporary/non-final state, usually due to visual or amount uncertainty. |
| `approved` | Commercial registered | Commercial registration is done. |
| `final_approved` | Final approved | Final approval is complete. |
| `rejected` | Rejected | Record is locked and removed from operational flow. |
| `incomplete` | Incomplete | Company staff cannot operate; customer must correct the record based on staff note. |
| `returned_commercial` | Returned to commercial | Finance returned the record to commercial. |
| `returned_finance` | Returned to finance | Commercial returned the record to finance. |
| `follow_up` | Follow-up | Record requires investigation, customer statement, or bank/account mismatch follow-up. |

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

Allowed commercial decisions:

- Register commercial: status becomes `approved`; notification color `#B5F1CC`.
- Temporary commercial registration: status becomes `temp_commercial`; notification color `#FEEAC9`.
- Return to finance: status becomes `returned_finance`; notification color `#DBEAFE`; record returns to operational dashboards.
- Reject: status becomes `rejected`; notification color `#FECACA`; record is locked from further operational action.
- Mark incomplete: status becomes `incomplete`; staff operations stop; customer must correct the record.
- Follow up: status becomes `follow_up`; used for mismatches, bank return cases, counterparty disagreement, or request for customer statement.
- Assign counterparty: sets `PaymentRecord.counterparty`; the receipt becomes visible to that counterparty.

Every commercial action should:

- validate user permission
- validate state transition
- save staff notes when applicable
- create `PaymentActivityLog`
- create relevant `UserNotification`
- keep history available to all authorized users

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

Customer sees "Under review" for:

- `pending`
- `commercial_review`
- `temp_commercial`
- `returned_commercial`
- `returned_finance`
- `follow_up`

Customer sees direct labels for:

- `approved`
- `final_approved`
- `rejected`
- `incomplete`

Decision:

- Internal workflow complexity should not be exposed to customers unless it helps them take action.
- `incomplete` must be clear because it requires customer correction.

### 4.8 Dashboard vs History

Business rule:

- Dashboards show items that need action.
- History shows all authorized records regardless of status.

Dashboard should include:

- new pending items
- returned items
- follow-up items
- items waiting for the current department's action

Dashboard should exclude:

- rejected records
- final approved records
- records already completed by the current department unless another department return/follow-up requires action

History should include:

- all records visible to the user by role/ownership rules
- all statuses, including rejected and completed records

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
| Temporary commercial registration | `#FEEAC9` |
| Counterparty approval | `#B5F1CC` |
| Counterparty return/follow-up | `#FEEAC9` |
| Counterparty rejection or payment rejection | `#FECACA` |
| Return to commercial | `#E9D5FF` |
| Return to finance | `#DBEAFE` |

Recommended categories:

- payment receipts
- returns and required actions
- counterparty
- orders and proformas
- invoices and price lists
- reconciliation
- warranty
- system/access

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
- current cache name in code: `rabasa-customer-pwa-v15`
- current static busting token: `ui-redesign-v15`

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
- `finance/pending-final-approval/`
- `finance/delegation/`
- `finance/bulk-approve/`

Commercial/status:

- `payments/<id>/status/`
- `payments/<id>/details-edit/`
- `payments/<id>/edit/`
- `payments/<id>/note/`

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
- Return-to-finance and return-to-commercial should move the record back to operational dashboards.
- Rejected records are locked out of operational flow.
- Incomplete records pause staff operations and require customer correction.
- History must show all authorized records with all statuses.
- Notifications must have color, category, unread/read behavior, and URL navigation.
- File download names must be consistent for image and PDF.
- Mobile UI changes must not break desktop UI.
- Desktop UI changes must not leak into mobile UI.
- Model changes require migration and database migration execution.
- Static/CSS/JS changes may require cache-busting and `collectstatic`.

## 22. Test Scenarios

Payment receipt:

1. Customer uploads image receipt.
2. Customer uploads PDF receipt.
3. Customer enters tracking code that contains non-numeric characters.
4. Commercial registers the payment.
5. Commercial marks temporary registration.
6. Commercial marks incomplete; customer edits and resubmits.
7. Commercial rejects; record becomes non-operational.
8. Finance registers payment.
9. Finance returns to commercial.
10. Commercial returns to finance.
11. Counterparty approves.
12. Counterparty returns or rejects.
13. Each step updates history and notifications.

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

