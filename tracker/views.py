from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate, logout
from .models import DriverProfile


def welcome_view(request):
    # If the driver is already logged in, bounce them straight to their logger
    if request.user.is_authenticated:
        return redirect('trip_log')
    return render(request, 'tracker/welcome.html')


def register_view(request):
    if request.method == 'POST':
        driver_name = request.POST.get('driver_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        llc_name = request.POST.get('llc_name', '').strip()
        truck_number = request.POST.get('truck_number', '').strip()
        password = request.POST.get('password')

        # Check if email/user already exists
        if User.objects.filter(username=email).exists():
            return render(request, 'tracker/register.html', {
                'error': 'An account with that email already exists.'
            })

        # 1. Create standard Django user
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=driver_name
        )

        # 2. Attach the rig and profile details
        DriverProfile.objects.create(
            user=user,
            phone=phone,
            llc_name=llc_name,
            truck_number=truck_number
        )

        # 3. Log them in directly
        login(request, user)

        # Redirect straight to the trip entry screen
        return redirect('trip_log')

    return render(request, 'tracker/register.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('trip_log')

    error = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return redirect('trip_log')
        else:
            error = 'Invalid email or password.'

    return render(request, 'tracker/login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('home')


def trip_log_view(request):
    # Placeholder for the daily trip logger card
    return render(request, 'tracker/trip_log.html')