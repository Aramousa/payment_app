import jdatetime
from io import BytesIO
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from .models import DailyPaymentPlan, InvoiceRecord, PaymentActivityLog, PaymentReceipt, PaymentRecord, SystemActivityLog, UserNotification
from .views import _staff_status_choices_for_role


class InvoiceFlowTests(TestCase):
    def setUp(self):
        self.commercial_user = User.objects.create_user(
            username='commercial1',
            password='pass1234',
            first_name='کاربر',
            last_name='بازرگانی',
        )
        self.commercial_user.profile.phone = '09120000001'
        self.commercial_user.profile.role = 'commercial'
        self.commercial_user.profile.can_upload_invoices = True
        self.commercial_user.profile.can_view_invoices = True
        self.commercial_user.profile.save()

        self.finance_user = User.objects.create_user(
            username='finance1',
            password='pass1234',
            first_name='Ú©Ø§Ø±Ø¨Ø±',
            last_name='Ù…Ø§Ù„ÛŒ',
        )
        self.finance_user.profile.role = 'finance'
        self.finance_user.profile.force_password_change = False
        self.finance_user.profile.save()

        self.data_entry_user = User.objects.create_user(
            username='dataentry1',
            password='pass1234',
            first_name='کاربر',
            last_name='ورود اطلاعات',
        )
        self.data_entry_user.profile.role = 'data_entry'
        self.data_entry_user.profile.can_edit_payment_details = True
        self.data_entry_user.profile.force_password_change = False
        self.data_entry_user.profile.save()

        self.customer_user = User.objects.create_user(
            username='customer1',
            password='pass1234',
            first_name='علی',
            last_name='مشتری',
        )
        self.customer_profile = self.customer_user.profile
        self.customer_profile.phone = '09120000002'
        self.customer_profile.organization = 'شرکت آلفا'
        self.customer_profile.city = 'تهران'
        self.customer_profile.role = 'customer'
        self.customer_profile.force_password_change = False
        self.customer_profile.save()

        self.other_customer = User.objects.create_user(
            username='customer2',
            password='pass1234',
            first_name='رضا',
            last_name='دیگری',
        )
        self.other_customer.profile.phone = '09120000003'
        self.other_customer.profile.organization = 'شرکت بتا'
        self.other_customer.profile.city = 'اصفهان'
        self.other_customer.profile.role = 'customer'
        self.other_customer.profile.force_password_change = False
        self.other_customer.profile.save()

    def test_commercial_user_can_upload_invoice_for_customer(self):
        self.client.login(username='commercial1', password='pass1234')
        response = self.client.post(
            reverse('invoices_dashboard'),
            {
                'customer': str(self.customer_profile.id),
                'invoice_date': '1405/02/08',
                'amount': '2,500,000',
                'invoice_number': 'INV-1001',
                'reference_number': 'REF-1001',
                'customer_visible_note': 'توضیح برای مشتری',
                'internal_note': 'یادداشت داخلی',
                'confirm_assignment': 'on',
                'attachment': SimpleUploadedFile('invoice.pdf', b'%PDF-1.4 sample', content_type='application/pdf'),
            },
        )

        self.assertEqual(response.status_code, 302)
        invoice = InvoiceRecord.objects.get(reference_number='REF-1001')
        self.assertEqual(invoice.customer, self.customer_user)
        self.assertEqual(invoice.uploaded_by, self.commercial_user)
        self.assertEqual(invoice.amount, 2500000)
        self.assertEqual(invoice.customer_visible_note, 'توضیح برای مشتری')
        self.assertEqual(invoice.internal_note, 'یادداشت داخلی')

    def test_customer_view_marks_invoice_seen_and_allows_note(self):
        invoice = InvoiceRecord.objects.create(
            customer=self.customer_user,
            uploaded_by=self.commercial_user,
            amount=900000,
            invoice_date=jdatetime.date(1405, 2, 8),
            reference_number='REF-2001',
            attachment=SimpleUploadedFile('invoice.pdf', b'%PDF-1.4 sample', content_type='application/pdf'),
            customer_visible_note='متن قابل مشاهده',
            internal_note='متن داخلی',
        )

        self.client.login(username='customer1', password='pass1234')
        detail_url = reverse('invoice_detail', args=[invoice.id])

        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'متن قابل مشاهده')
        self.assertNotContains(response, 'متن داخلی')
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.customer_seen_at)

        response = self.client.post(detail_url, {'customer_note': 'یادداشت تست'})
        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.customer_note, 'یادداشت تست')
        self.assertIsNotNone(invoice.customer_note_updated_at)

    def test_customer_cannot_access_other_customer_invoice(self):
        invoice = InvoiceRecord.objects.create(
            customer=self.other_customer,
            uploaded_by=self.commercial_user,
            amount=500000,
            invoice_date=jdatetime.date(1405, 2, 8),
            reference_number='REF-3001',
            attachment=SimpleUploadedFile('invoice.pdf', b'%PDF-1.4 sample', content_type='application/pdf'),
        )

        self.client.login(username='customer1', password='pass1234')
        response = self.client.get(reverse('invoice_detail', args=[invoice.id]))
        self.assertEqual(response.status_code, 403)

    def test_customer_invoice_list_only_contains_own_invoices(self):
        own_invoice = InvoiceRecord.objects.create(
            customer=self.customer_user,
            uploaded_by=self.commercial_user,
            amount=700000,
            invoice_date=jdatetime.date(1405, 2, 8),
            invoice_number='INV-OWN',
            reference_number='REF-OWN',
            attachment=SimpleUploadedFile('own.pdf', b'%PDF-1.4 own', content_type='application/pdf'),
        )
        other_invoice = InvoiceRecord.objects.create(
            customer=self.other_customer,
            uploaded_by=self.commercial_user,
            amount=800000,
            invoice_date=jdatetime.date(1405, 2, 8),
            invoice_number='INV-OTHER',
            reference_number='REF-OTHER',
            attachment=SimpleUploadedFile('other.pdf', b'%PDF-1.4 other', content_type='application/pdf'),
        )

        self.client.login(username='customer1', password='pass1234')
        response = self.client.get(reverse('invoices_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_invoice.invoice_number)
        self.assertNotContains(response, other_invoice.invoice_number)

    def test_customer_cannot_access_other_customer_invoice_file(self):
        invoice = InvoiceRecord.objects.create(
            customer=self.other_customer,
            uploaded_by=self.commercial_user,
            amount=500000,
            invoice_date=jdatetime.date(1405, 2, 8),
            invoice_number='INV-FILE-OTHER',
            reference_number='REF-FILE-OTHER',
            attachment=SimpleUploadedFile('other-file.pdf', b'%PDF-1.4 other', content_type='application/pdf'),
        )

        self.client.login(username='customer1', password='pass1234')
        response = self.client.get(reverse('invoice_file', args=[invoice.id]))
        self.assertEqual(response.status_code, 403)

    def test_customer_payment_list_and_receipt_file_are_scoped_to_owner(self):
        own_payment = PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='علی',
            last_name='مشتری',
            organization='شرکت آلفا',
            city='تهران',
            phone='09120000002',
            amount=100000,
            pay_date=jdatetime.date(1405, 2, 8),
            tracking_code='PAY-OWN',
        )
        other_payment = PaymentRecord.objects.create(
            user=self.other_customer,
            first_name='رضا',
            last_name='دیگری',
            organization='شرکت بتا',
            city='اصفهان',
            phone='09120000003',
            amount=200000,
            pay_date=jdatetime.date(1405, 2, 8),
            tracking_code='PAY-OTHER',
        )
        other_receipt = PaymentReceipt.objects.create(
            payment=other_payment,
            image=SimpleUploadedFile('other-receipt.pdf', b'%PDF-1.4 receipt', content_type='application/pdf'),
            file_hash='other-receipt-hash',
        )

        self.client.login(username='customer1', password='pass1234')
        response = self.client.get(reverse('submit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_payment.tracking_code)
        self.assertNotContains(response, other_payment.tracking_code)

        response = self.client.get(reverse('payment_timeline', args=[other_payment.id]))
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse('receipt_file', args=[other_receipt.id]))
        self.assertEqual(response.status_code, 403)

    def test_payment_workflow_active_queue_history_and_logs(self):
        payment = PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='Ali',
            last_name='Customer',
            organization='Alpha',
            city='Tehran',
            phone='09120000002',
            amount=100000,
            pay_date=jdatetime.date(1405, 2, 8),
            tracking_code='WF-APPROVE',
        )

        self.client.login(username='commercial1', password='pass1234')
        response = self.client.get(reverse('submit'))
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_COMMERCIAL_REVIEW)
        self.assertTrue(
            PaymentActivityLog.objects.filter(
                payment=payment,
                actor=self.commercial_user,
                action=PaymentActivityLog.ACTION_STATUS_CHANGED,
                to_status=PaymentRecord.STATUS_COMMERCIAL_REVIEW,
            ).exists()
        )
        self.assertTrue(
            PaymentActivityLog.objects.filter(
                payment=payment,
                actor=self.commercial_user,
                action=PaymentActivityLog.ACTION_VIEWED,
            ).exists()
        )

        response = self.client.post(
            reverse('staff_update_status', args=[payment.id]),
            {'status': PaymentRecord.STATUS_APPROVED, 'note': '', 'next': reverse('submit')},
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_APPROVED)

        response = self.client.get(reverse('submit'))
        self.assertNotContains(response, 'WF-APPROVE')
        response = self.client.get(reverse('payment_history'))
        self.assertContains(response, 'WF-APPROVE')

        self.client.logout()
        self.client.login(username='finance1', password='pass1234')
        response = self.client.get(reverse('submit'))
        self.assertContains(response, 'WF-APPROVE')

        response = self.client.post(
            reverse('staff_update_status', args=[payment.id]),
            {'status': PaymentRecord.STATUS_FINAL_APPROVED, 'note': '', 'next': reverse('submit')},
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_FINAL_APPROVED)

        response = self.client.get(reverse('submit'))
        self.assertNotContains(response, 'WF-APPROVE')
        response = self.client.get(reverse('payment_history'))
        self.assertContains(response, 'WF-APPROVE')

    def test_staff_status_choices_for_generic_staff_role_are_not_empty(self):
        choices = _staff_status_choices_for_role('staff')
        self.assertTrue(len(choices) > 0)
        self.assertIn((PaymentRecord.STATUS_APPROVED, 'ثبت بازرگانی'), choices)

    def test_dashboard_notification_bell_is_visible_for_staff_roles(self):
        self.client.login(username='commercial1', password='pass1234')
        response = self.client.get(reverse('submit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'notification-bell')

        self.client.logout()
        self.client.login(username='finance1', password='pass1234')
        response = self.client.get(reverse('submit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'notification-bell')

    def test_status_changes_create_user_notifications_and_feed_marks_read(self):
        payment = PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='Ali',
            last_name='Customer',
            organization='Alpha',
            city='Tehran',
            phone='09120000002',
            amount=100000,
            pay_date=jdatetime.date(1405, 2, 8),
            tracking_code='NOTIFY-INCOMPLETE',
            status=PaymentRecord.STATUS_COMMERCIAL_REVIEW,
        )

        self.client.login(username='commercial1', password='pass1234')
        response = self.client.post(
            reverse('staff_update_status', args=[payment.id]),
            {'status': PaymentRecord.STATUS_INCOMPLETE, 'note': 'Needs correction', 'next': reverse('submit')},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.customer_user,
                category=UserNotification.CATEGORY_PAYMENT,
                title='تغییر وضعیت فیش',
                is_read=False,
            ).exists()
        )

        self.client.logout()
        self.client.login(username='customer1', password='pass1234')
        response = self.client.get(reverse('notifications_feed'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['unread_count'], 1)
        self.assertEqual(payload['items'][0]['title'], 'تغییر وضعیت فیش')

        response = self.client.post(reverse('notifications_mark_read'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(UserNotification.objects.filter(user=self.customer_user, is_read=False).count(), 0)

    def test_customer_sees_commercial_and_final_approval_as_distinct_statuses(self):
        commercial_payment = PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='Ali',
            last_name='Customer',
            organization='Alpha',
            city='Tehran',
            phone='09120000002',
            amount=100000,
            pay_date=jdatetime.date(1405, 2, 8),
            tracking_code='CUSTOMER-COMMERCIAL',
            status=PaymentRecord.STATUS_APPROVED,
        )
        final_payment = PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='Ali',
            last_name='Customer',
            organization='Alpha',
            city='Tehran',
            phone='09120000002',
            amount=200000,
            pay_date=jdatetime.date(1405, 2, 9),
            tracking_code='CUSTOMER-FINAL',
            status=PaymentRecord.STATUS_FINAL_APPROVED,
        )

        self.client.login(username='customer1', password='pass1234')
        response = self.client.get(reverse('submit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, commercial_payment.tracking_code)
        self.assertContains(response, final_payment.tracking_code)
        self.assertContains(response, 'ثبت بازرگانی')
        self.assertContains(response, 'تایید نهایی')
        self.assertContains(response, 'flag-orange')
        self.assertContains(response, 'flag-green')

    def test_payment_list_shows_commercial_and_finance_status_columns_for_customer(self):
        PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='Ali',
            last_name='Customer',
            organization='Alpha',
            city='Tehran',
            phone='09120000002',
            amount=100000,
            pay_date=jdatetime.date(1405, 2, 8),
            tracking_code='DUAL-STATUS',
            status=PaymentRecord.STATUS_APPROVED,
        )

        self.client.login(username='customer1', password='pass1234')
        response = self.client.get(reverse('submit'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'وضعیت بازرگانی')
        self.assertContains(response, 'وضعیت مالی')
        self.assertContains(response, 'ثبت بازرگانی')
        self.assertContains(response, 'در انتظار تایید مالی')

    def test_staff_status_choices_for_commercial_role(self):
        choices = _staff_status_choices_for_role('commercial')
        self.assertEqual(
            choices,
            [
                (PaymentRecord.STATUS_APPROVED, 'ثبت بازرگانی'),
                (PaymentRecord.STATUS_INCOMPLETE, 'ناقص'),
                (PaymentRecord.STATUS_REJECTED, 'رد شده'),
            ]
        )

    def test_staff_status_choices_for_finance_role(self):
        choices = _staff_status_choices_for_role('finance')
        self.assertEqual(
            choices,
            [
                (PaymentRecord.STATUS_FINAL_APPROVED, 'تایید نهایی'),
                (PaymentRecord.STATUS_RETURNED_TO_COMMERCIAL, 'عودت به بازرگانی'),
            ]
        )

    def test_finance_can_see_pending_but_cannot_change_until_commercial_approval(self):
        payment = PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='Ali',
            last_name='Customer',
            organization='Alpha',
            city='Tehran',
            phone='09120000002',
            amount=100000,
            pay_date=jdatetime.date(1405, 2, 8),
            tracking_code='WF-PENDING',
        )

        self.client.login(username='finance1', password='pass1234')
        response = self.client.get(reverse('submit'))
        self.assertContains(response, 'WF-PENDING')

        response = self.client.post(
            reverse('staff_update_status', args=[payment.id]),
            {'status': PaymentRecord.STATUS_FINAL_APPROVED, 'note': '', 'next': reverse('submit')},
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_PENDING)

    def test_excel_export_defaults_to_all_fields_and_accepts_selected_fields(self):
        for index in range(11):
            PaymentRecord.objects.create(
                user=self.customer_user,
                first_name='Ali',
                last_name='Customer',
                organization='Alpha',
                city='Tehran',
                phone='09120000002',
                amount=100000 + index,
                pay_date=jdatetime.date(1405, 2, 8),
                tracking_code=f'EXPORT-{index + 1}',
            )

        self.client.login(username='commercial1', password='pass1234')
        response = self.client.get(reverse('export_data', args=['payments']))
        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response['Content-Disposition'],
            r'filename="payments_\d{8}_\d{6}\.xlsx"',
        )
        workbook = load_workbook(BytesIO(response.content))
        headers = [cell.value for cell in workbook.active[1]]
        self.assertIn('کد پیگیری', headers)
        self.assertIn('مبلغ', headers)

        response = self.client.get(
            reverse('export_data', args=['payments']),
            {'fields': ['tracking_code', 'amount']},
        )
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        headers = [cell.value for cell in workbook.active[1]]
        self.assertEqual(headers, ['مبلغ', 'کد پیگیری'])

        response = self.client.get(
            reverse('export_data', args=['payments']),
            {'fields': ['tracking_code'], 'scope': 'page', 'per_page': '10', 'page': '1'},
        )
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        rows = list(workbook.active.iter_rows(values_only=True))
        self.assertEqual(rows[0], ('کد پیگیری',))
        self.assertEqual(len(rows), 11)

    def test_daily_payment_plans_support_day_week_month_views_and_export_period(self):
        base_date = jdatetime.date(1405, 2, 10)
        DailyPaymentPlan.objects.create(
            deposit_date=base_date,
            bank_name='Bank',
            account_number='ACC-DAY',
            total_expected_amount=100000,
            created_by=self.commercial_user,
        )
        DailyPaymentPlan.objects.create(
            deposit_date=base_date + jdatetime.timedelta(days=1),
            bank_name='Bank',
            account_number='ACC-MONTH',
            total_expected_amount=200000,
            created_by=self.commercial_user,
        )
        DailyPaymentPlan.objects.create(
            deposit_date=base_date - jdatetime.timedelta(days=20),
            bank_name='Bank',
            account_number='ACC-PAST',
            total_expected_amount=150000,
            created_by=self.commercial_user,
        )
        DailyPaymentPlan.objects.create(
            deposit_date=jdatetime.date(1405, 3, 1),
            bank_name='Bank',
            account_number='ACC-NEXT',
            total_expected_amount=300000,
            created_by=self.commercial_user,
        )

        self.client.login(username='commercial1', password='pass1234')
        response = self.client.get(reverse('daily_payment_plans'), {'mode': 'day', 'date': '1405/02/10'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ACC-DAY')
        self.assertNotContains(response, 'ACC-MONTH')

        response = self.client.get(reverse('daily_payment_plans'), {'mode': 'week', 'date': '1405/02/10'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ACC-DAY')
        self.assertNotContains(response, 'ACC-MONTH')
        self.assertNotContains(response, 'ACC-PAST')

        response = self.client.get(reverse('daily_payment_plans'), {'mode': 'month', 'date': '1405/02/10'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ACC-DAY')
        self.assertContains(response, 'ACC-PAST')
        self.assertNotContains(response, 'ACC-MONTH')
        self.assertNotContains(response, 'ACC-NEXT')

        response = self.client.get(
            reverse('daily_payment_plans'),
            {'mode': 'range', 'date': '1405/02/11', 'start_date': '1405/02/11', 'end_date': '1405/03/01'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ACC-MONTH')
        self.assertContains(response, 'ACC-NEXT')
        self.assertNotContains(response, 'ACC-DAY')
        self.assertNotContains(response, 'ACC-PAST')

        response = self.client.get(
            reverse('export_data', args=['daily_plans']),
            {
                'mode': 'range',
                'date': '1405/02/11',
                'start_date': '1405/02/11',
                'end_date': '1405/03/01',
                'fields': ['account_number'],
            },
        )
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        rows = list(workbook.active.iter_rows(values_only=True))
        exported_accounts = [row[0] for row in rows[1:]]
        self.assertIn('ACC-MONTH', exported_accounts)
        self.assertIn('ACC-NEXT', exported_accounts)
        self.assertNotIn('ACC-DAY', exported_accounts)

    def test_data_entry_user_can_complete_payment_details_and_changes_are_logged(self):
        payment = PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='Ali',
            last_name='Customer',
            organization='Alpha',
            city='Tehran',
            phone='09120000002',
            amount=0,
            tracking_code='',
        )

        self.client.login(username='dataentry1', password='pass1234')
        response = self.client.get(reverse('submit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('staff_edit_payment_details', args=[payment.id]))

        response = self.client.post(
            reverse('staff_edit_payment_details', args=[payment.id]),
            {
                'payer_account_number': '111222333',
                'payer_full_name': 'Ali Customer',
                'payer_bank_name': 'Melli',
                'beneficiary_bank_name': 'Saderat',
                'beneficiary_account_number': '444555666',
                'beneficiary_account_owner': 'Company',
                'amount': '250000',
                'tracking_code': 'TRACK-250',
                'pay_date': '1405/02/08',
                'next': reverse('submit'),
            },
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_PENDING)
        self.assertEqual(payment.tracking_code, 'TRACK-250')
        self.assertEqual(payment.amount, 250000)

        log = PaymentActivityLog.objects.filter(
            payment=payment,
            actor=self.data_entry_user,
            action=PaymentActivityLog.ACTION_EDITED,
        ).latest('created_at')
        self.assertEqual(log.from_status, PaymentRecord.STATUS_PENDING)
        self.assertEqual(log.to_status, PaymentRecord.STATUS_PENDING)
        self.assertIn('کد پیگیری', log.note)
        self.assertIn('TRACK-250', log.note)

    def test_data_entry_user_cannot_change_status_and_only_sees_detail_edit_action(self):
        payment = PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='Ali',
            last_name='Customer',
            organization='Alpha',
            city='Tehran',
            phone='09120000002',
            amount=100000,
            pay_date=jdatetime.date(1405, 2, 8),
            tracking_code='DATAENTRY-NO-STATUS',
            status=PaymentRecord.STATUS_PENDING,
        )

        self.client.login(username='dataentry1', password='pass1234')
        response = self.client.get(reverse('submit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('staff_edit_payment_details', args=[payment.id]))
        self.assertNotContains(response, reverse('staff_update_status', args=[payment.id]))
        self.assertNotContains(response, 'تغییر وضعیت و توضیح')

        response = self.client.post(
            reverse('staff_update_status', args=[payment.id]),
            {'status': PaymentRecord.STATUS_APPROVED, 'note': '', 'next': reverse('submit')},
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_PENDING)

    def test_user_without_payment_detail_permission_cannot_edit_customer_payment_details(self):
        payment = PaymentRecord.objects.create(
            user=self.customer_user,
            first_name='Ali',
            last_name='Customer',
            organization='Alpha',
            city='Tehran',
            phone='09120000002',
            amount=100000,
            tracking_code='NO-EDIT',
        )

        self.client.login(username='commercial1', password='pass1234')
        response = self.client.get(reverse('staff_edit_payment_details', args=[payment.id]))
        self.assertEqual(response.status_code, 403)

    def test_uploaded_files_are_not_served_from_direct_media_url(self):
        invoice = InvoiceRecord.objects.create(
            customer=self.customer_user,
            uploaded_by=self.commercial_user,
            amount=500000,
            invoice_date=jdatetime.date(1405, 2, 8),
            invoice_number='INV-MEDIA',
            reference_number='REF-MEDIA',
            attachment=SimpleUploadedFile('media-direct.pdf', b'%PDF-1.4 media', content_type='application/pdf'),
        )

        self.client.login(username='customer1', password='pass1234')
        response = self.client.get(invoice.attachment.url)
        self.assertEqual(response.status_code, 404)

    def test_customer_can_edit_optional_profile_fields_and_change_is_logged(self):
        self.client.login(username='customer1', password='pass1234')
        response = self.client.post(
            reverse('profile_edit'),
            {
                'email': 'customer1@example.com',
                'phone': '02122222222',
                'mobile': '09123333333',
                'second_mobile': '09124444444',
                'address': 'آدرس اصلی مشتری',
                'second_address': 'آدرس دوم مشتری',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.customer_user.refresh_from_db()
        self.customer_profile.refresh_from_db()
        self.assertEqual(self.customer_user.email, 'customer1@example.com')
        self.assertEqual(self.customer_profile.phone, '02122222222')
        self.assertEqual(self.customer_profile.second_mobile, '09124444444')
        self.assertEqual(self.customer_profile.second_address, 'آدرس دوم مشتری')

        log = SystemActivityLog.objects.get(action=SystemActivityLog.ACTION_PROFILE_UPDATED)
        self.assertEqual(log.actor, self.customer_user)
        self.assertEqual(log.target_user, self.customer_user)
        self.assertIn('شماره همراه دوم', log.description)
        self.assertIn('آدرس دوم', log.description)

    def test_customer_profile_optional_fields_can_be_empty(self):
        self.customer_user.email = 'old@example.com'
        self.customer_user.save(update_fields=['email'])
        self.customer_profile.phone = '02122222222'
        self.customer_profile.mobile = '09123333333'
        self.customer_profile.second_mobile = '09124444444'
        self.customer_profile.address = 'آدرس اصلی'
        self.customer_profile.second_address = 'آدرس دوم'
        self.customer_profile.save()

        self.client.login(username='customer1', password='pass1234')
        response = self.client.post(
            reverse('profile_edit'),
            {
                'email': '',
                'phone': '',
                'mobile': '',
                'second_mobile': '',
                'address': '',
                'second_address': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.customer_user.refresh_from_db()
        self.customer_profile.refresh_from_db()
        self.assertEqual(self.customer_user.email, '')
        self.assertEqual(self.customer_profile.phone, '')
        self.assertEqual(self.customer_profile.mobile, '')
        self.assertEqual(self.customer_profile.second_mobile, '')
        self.assertEqual(self.customer_profile.address, '')
        self.assertEqual(self.customer_profile.second_address, '')


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin1',
            password='pass1234',
            email='admin@example.com',
        )
        self.admin_user.profile.phone = '02100000000'
        self.admin_user.profile.save()

    def test_superuser_can_create_user_from_simple_management_page(self):
        self.client.login(username='admin1', password='pass1234')
        response = self.client.post(
            reverse('users_manage'),
            {
                'username': 'customer_new',
                'first_name': 'مهدی',
                'last_name': 'محمدی',
                'email': 'customer-new@example.com',
                'phone': '02111111111',
                'mobile': '09121111111',
                'province': 'تهران',
                'city': 'تهران',
                'address': 'خیابان نمونه',
                'organization': 'شرکت نمونه',
                'password': 'Ab123',
                'role': 'customer',
                'active_from': '1405/02/08',
                'valid_until': '1405/12/29',
                'force_password_change': 'on',
                'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        created_user = User.objects.get(username='09121111111')
        self.assertEqual(created_user.first_name, 'مهدی')
        self.assertEqual(created_user.email, 'customer-new@example.com')
        self.assertEqual(created_user.profile.mobile, '09121111111')
        self.assertEqual(created_user.profile.role, 'customer')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_emails_password_logs_without_storing_password_and_forces_change(self):
        target = User.objects.create_user(
            username='customer_reset',
            password='Old123',
            email='customer-reset@example.com',
        )
        target.profile.role = 'customer'
        target.profile.force_password_change = False
        target.profile.save()

        self.client.login(username='admin1', password='pass1234')
        response = self.client.post(reverse('reset_user_password', args=[target.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        temp_password = payload['temp_password']
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(temp_password, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['customer-reset@example.com'])

        target.refresh_from_db()
        self.assertTrue(target.check_password(temp_password))
        self.assertTrue(target.profile.force_password_change)

        log = SystemActivityLog.objects.get(action=SystemActivityLog.ACTION_PASSWORD_RESET)
        self.assertEqual(log.actor, self.admin_user)
        self.assertEqual(log.target_user, target)
        self.assertNotIn(temp_password, log.description)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_without_target_email_still_changes_password_and_logs_it(self):
        target = User.objects.create_user(
            username='customer_no_email',
            password='Old123',
            email='',
        )
        target.profile.role = 'customer'
        target.profile.force_password_change = False
        target.profile.save()

        self.client.login(username='admin1', password='pass1234')
        response = self.client.post(reverse('reset_user_password', args=[target.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        temp_password = payload['temp_password']
        target.refresh_from_db()
        self.assertTrue(target.check_password(temp_password))
        self.assertTrue(target.profile.force_password_change)
        self.assertEqual(len(mail.outbox), 0)
        log = SystemActivityLog.objects.get(target_user=target, action=SystemActivityLog.ACTION_PASSWORD_RESET)
        self.assertNotIn(temp_password, log.description)
        self.assertIn('ایمیل ثبت نشده است', log.description)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='invalid.localhost')
    def test_password_reset_continues_when_email_delivery_fails(self):
        target = User.objects.create_user(
            username='customer_email_fails',
            password='Old123',
            email='customer-fail@example.com',
        )
        target.profile.role = 'customer'
        target.profile.force_password_change = False
        target.profile.save()

        self.client.login(username='admin1', password='pass1234')
        response = self.client.post(reverse('reset_user_password', args=[target.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        temp_password = payload['temp_password']
        self.assertIn('ارسال ایمیل انجام نشد', payload['message'])

        target.refresh_from_db()
        self.assertTrue(target.check_password(temp_password))
        self.assertTrue(target.profile.force_password_change)

        log = SystemActivityLog.objects.get(target_user=target, action=SystemActivityLog.ACTION_PASSWORD_RESET)
        self.assertNotIn(temp_password, log.description)
        self.assertIn('ارسال ایمیل انجام نشد', log.description)
