from datetime import timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from .models import DriverProfile, Trip


def welcome_view(request):
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

        if User.objects.filter(username=email).exists():
            return render(request, 'tracker/register.html', {
                'error': 'An account with that email already exists.'
            })

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=driver_name
        )

        DriverProfile.objects.create(
            user=user,
            phone=phone,
            llc_name=llc_name,
            truck_number=truck_number
        )

        login(request, user)
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
        # Accept either pickup_date or fall back to trip_date if named in the template
        pickup_date = request.POST.get('pickup_date') or request.POST.get('trip_date') or None
        bol_number = request.POST.get('bol_number', '').strip()
        origin_city = request.POST.get('origin_city', '').strip()
        destination_city = request.POST.get('destination_city', '').strip()
        miles_total = request.POST.get('miles_total') or 0.0
        fuel_gallons = request.POST.get('fuel_gallons') or None
        fuel_cost = request.POST.get('fuel_cost') or None
        notes = request.POST.get('notes', '').strip()

        Trip.objects.create(
            driver=request.user,
            pickup_date=pickup_date,
            bol_number=bol_number,
            origin_city=origin_city,
            destination_city=destination_city,
            miles_total=miles_total,
            fuel_gallons=fuel_gallons,
            fuel_cost=fuel_cost,
            notes=notes,
            status='Delivered'
        )
        return redirect('trip_log')

    trips = Trip.objects.filter(driver=request.user)

    # 1. Miles this week (last 7 days by pickup_date)
    seven_days_ago = timezone.now().date() - timedelta(days=7)
    recent_trips = trips.filter(pickup_date__gte=seven_days_ago)
    
    weekly_sum = recent_trips.aggregate(Sum('miles_total'))['miles_total__sum']
    if weekly_sum is not None:
        miles_this_week = weekly_sum
    else:
        # Fallback to the latest 7 trips if none in the past 7 days
        fallback_trips = trips[:7]
        miles_this_week = sum(t.miles_total or 0 for t in fallback_trips)

    # 2. Avg fuel efficiency (total miles / total gallons)
    total_lifetime_miles = trips.aggregate(Sum('miles_total'))['miles_total__sum'] or 0
    total_gallons = trips.aggregate(Sum('fuel_gallons'))['fuel_gallons__sum'] or 0
    
    avg_mpg = (
        round(float(total_lifetime_miles) / float(total_gallons), 1)
        if total_gallons and total_gallons > 0
        else 0.0
    )

    # 3. Active settlements
    active_settlements = trips.aggregate(Sum('payout'))['payout__sum'] or 0.00

    context = {
        'trips': trips,
        'miles_this_week': miles_this_week,
        'avg_mpg': avg_mpg,
        'active_settlements': active_settlements,
    }
    return render(request, 'tracker/trip_log.html', context)