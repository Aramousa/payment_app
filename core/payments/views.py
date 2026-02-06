from django.shortcuts import render, redirect
from .forms import PaymentRecordForm
from .models import PaymentRecord

def create_payment(request):
    if request.method == 'POST':
        form = PaymentRecordForm(request.POST, request.FILES)
        if form.is_valid():
            payment = form.save(commit=False)
            if request.user.is_authenticated:
                payment.user = request.user
            payment.save()
            return redirect('success')
    else:
        form = PaymentRecordForm()

    records = PaymentRecord.objects.all().order_by('-id')

    return render(request, 'payments/form.html', {
        'form': form,
        'records': records
    })


def success(request):
    records = PaymentRecord.objects.all().order_by('-id')
    return render(request, 'payments/success.html', {
        'records': records
    })
