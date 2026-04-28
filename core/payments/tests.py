import jdatetime
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import InvoiceRecord


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
                'phone': '02111111111',
                'mobile': '09121111111',
                'province': 'تهران',
                'city': 'تهران',
                'address': 'خیابان نمونه',
                'organization': 'شرکت نمونه',
                'password': '12345',
                'role': 'customer',
                'active_from': '1405/02/08',
                'valid_until': '1405/12/29',
                'force_password_change': 'on',
                'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        created_user = User.objects.get(username='customer_new')
        self.assertEqual(created_user.first_name, 'مهدی')
        self.assertEqual(created_user.profile.mobile, '09121111111')
        self.assertEqual(created_user.profile.role, 'customer')
