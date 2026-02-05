from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import PaymentRecordForm

#@login_required
def create_payment(request):
    if request.method == 'POST':
        form = PaymentRecordForm(request.POST, request.FILES)
        if form.is_valid():
            payment = form.save(commit=False)
            if request.user.is_authenticated:   # فقط اگر لاگین بود
                payment.user = request.user
            payment.save()
            return redirect('success')
    else:
        form = PaymentRecordForm()

    return render(request, 'payments/form.html', {'form': form})


#@login_required
def success(request):
    return render(request, 'payments/success.html')
