from datetime import timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from .models import DriverProfile, Trip


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


@login_required(login_url='login')
def trip_log_view(request):
    if request.method == 'POST':
        trip_date = request.POST.get('trip_date') or None
        bol_number = request.POST.get('bol_number', '').strip()
        origin_city = request.POST.get('origin_city', '').strip()
        destination_city = request.POST.get('destination_city', '').strip()
        start_odometer = request.POST.get('start_odometer') or 0.0
        end_odometer = request.POST.get('end_odometer') or 0.0
        fuel_gallons = request.POST.get('fuel_gallons') or None
        fuel_cost = request.POST.get('fuel_cost') or None
        notes = request.POST.get('notes', '').strip()

        Trip.objects.create(
            driver=request.user,
            trip_date=trip_date,
            bol_number=bol_number,
            origin_city=origin_city,
            destination_city=destination_city,
            start_odometer=start_odometer,
            end_odometer=end_odometer,
            fuel_gallons=fuel_gallons,
            fuel_cost=fuel_cost,
            notes=notes,
            status='Delivered'
        )
        return redirect('trip_log')

    # Fetch only the logged-in driver's trips
    trips = Trip.objects.filter(driver=request.user)

    # 1. Miles this week (last 7 days)
    seven_days_ago = timezone.now().date() - timedelta(days=7)
    recent_trips = trips.filter(trip_date__gte=seven_days_ago)
    miles_this_week = sum(t.total_miles for t in recent_trips) if recent_trips.exists() else sum(t.total_miles for t in trips[:7])

    # 2. Avg fuel efficiency (total miles / total gallons)
    total_lifetime_miles = sum(t.total_miles for t in trips)
    total_gallons = trips.aggregate(Sum('fuel_gallons'))['fuel_gallons__sum'] or 0
    avg_mpg = round(float(total_lifetime_miles) / float(total_gallons), 1) if total_gallons and total_gallons > 0 else 0.0

    # 3. Active settlements
    active_settlements = trips.aggregate(Sum('payout'))['payout__sum'] or 0.00

    context = {
        'trips': trips,
        'miles_this_week': miles_this_week,
        'avg_mpg': avg_mpg,
        'active_settlements': active_settlements,
    }
    return render(request, 'tracker/trip_log.html', context)
