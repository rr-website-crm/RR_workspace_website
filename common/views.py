from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone

def home(request):
    """Landing page without login"""
    return render(request, 'common/home.html')

@login_required
def home_dashboard(request):
    """Home dashboard after login"""
    # user = request.user
    context = {
        'user': request.user,
        'today_date': timezone.localdate(),
    }
    return render(request, 'common/home_dashboard.html', context)
