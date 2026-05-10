import jdatetime
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from .models import InvoiceRecord, PaymentReceipt, PaymentRecord, SystemActivityLog


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
