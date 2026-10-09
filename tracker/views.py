from datetime import timedelta
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.utils import timezone
from .models import DriverProfile, Trip, FuelStop


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
def customer_warning_check(request):
    """Endpoint for instant lookup of prior driver notes on a customer."""
    query = request.GET.get('name', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'warnings': []})

    trips_with_notes = (
        Trip.objects.filter(driver=request.user, customer_name__icontains=query)
        .exclude(notes__exact='')
        .order_by('-pickup_date')[:5]
    )

    red_flags = ['pain', 'trouble', 'avoid', 'slow', 'detention', 'bad', 'refused', 'waste', 'late', 'dock']
    warnings = []

    for trip in trips_with_notes:
        note_lower = trip.notes.lower()
        is_red_flag = any(flag in note_lower for flag in red_flags)
        warnings.append({
            'date': trip.pickup_date.strftime('%b %d, %Y') if trip.pickup_date else 'Past Trip',
            'trip_number': trip.trip_number or trip.bol_number or 'N/A',
            'notes': trip.notes,
            'is_red_flag': is_red_flag,
        })

    return JsonResponse({'warnings': warnings})


@login_required(login_url='login')
def trip_log_view(request):
    if request.method == 'POST':
        # Header / Rates & Mileage
        trip_number = request.POST.get('trip_number', '').strip()
        bol_number = request.POST.get('bol_number', '').strip()
        payout = request.POST.get('payout') or Decimal('0.00')
        fuel_surcharge = request.POST.get('fuel_surcharge') or Decimal('0.00')
        miles_total = request.POST.get('miles_total') or Decimal('0.0')
        deadhead_miles = request.POST.get('deadhead_miles') or Decimal('0.0')

        # Origin & Pickup
        origin_city = request.POST.get('origin_city', '').strip()
        pickup_date = request.POST.get('pickup_date') or None
        pickup_arrival = request.POST.get('pickup_arrival') or None
        pickup_departure = request.POST.get('pickup_departure') or None

        # Surcharge Deductions & Trip Expenses
        def_cost = request.POST.get('def_cost') or Decimal('0.00')
        reefer_cost = request.POST.get('reefer_cost') or Decimal('0.00')
        cat_scale = request.POST.get('cat_scale') or Decimal('0.00')
        incidentals = request.POST.get('incidentals') or Decimal('0.00')

        # Destination & Delivery
        destination_city = request.POST.get('destination_city', '').strip()
        destination_date = request.POST.get('destination_date') or request.POST.get('delivery_date') or None
        destination_arrival = request.POST.get('destination_arrival') or None
        destination_departure = request.POST.get('destination_departure') or None

        # Customer & Notes
        customer_name = request.POST.get('customer_name', '').strip()
        notes = request.POST.get('notes', '').strip()

        # Trip Status
        if 'plan_mission' in request.POST:
            status = 'Quote / Planner'
        elif 'complete_trip' in request.POST:
            status = 'Delivered'
        else:
            status = 'In Transit'

        # 1. Create the main Trip record
        trip = Trip.objects.create(
            driver=request.user,
            trip_number=trip_number,
            bol_number=bol_number,
            payout=payout,
            fuel_surcharge=fuel_surcharge,
            miles_total=miles_total,
            deadhead_miles=deadhead_miles,
            origin_city=origin_city,
            pickup_date=pickup_date,
            pickup_arrival=pickup_arrival,
            pickup_departure=pickup_departure,
            def_cost=def_cost,
            reefer_cost=reefer_cost,
            cat_scale=cat_scale,
            incidentals=incidentals,
            destination_city=destination_city,
            destination_date=destination_date,
            destination_arrival=destination_arrival,
            destination_departure=destination_departure,
            customer_name=customer_name,
            notes=notes,
            status=status
        )

        # 2. Save individual fuel stop lines if submitted
        locations = request.POST.getlist('stop_location[]')
        gallons_list = request.POST.getlist('fuel_gallons[]')
        prices_list = request.POST.getlist('fuel_price[]')

        for loc, gal, price in zip(locations, gallons_list, prices_list):
            if gal and price:
                try:
                    FuelStop.objects.create(
                        trip=trip,
                        stop_location=loc.strip(),
                        gallons=Decimal(gal),
                        price_per_gallon=Decimal(price)
                    )
                except (ValueError, TypeError):
                    pass

        return redirect('trip_log')

    # Query all trips for the history table
    all_trips = Trip.objects.filter(driver=request.user)

    # Exclude Quotes / Planned Missions from actual historical metrics
    actual_trips = all_trips.exclude(status='Quote / Planner')

    # 1. Miles this week (last 7 days by pickup_date)
    seven_days_ago = timezone.now().date() - timedelta(days=7)
    recent_trips = actual_trips.filter(pickup_date__gte=seven_days_ago)

    weekly_sum = recent_trips.aggregate(Sum('miles_total'))['miles_total__sum']
    if weekly_sum is not None:
        miles_this_week = weekly_sum
    else:
        fallback_trips = actual_trips[:7]
        miles_this_week = sum(t.miles_total or Decimal('0.0') for t in fallback_trips)

    # 2. Avg fuel efficiency (actual lifetime miles / actual fuel stop gallons)
    total_lifetime_miles = actual_trips.aggregate(Sum('miles_total'))['miles_total__sum'] or Decimal('0.0')
    total_stop_gallons = FuelStop.objects.filter(
        trip__driver=request.user,
        trip__status__in=['In Transit', 'Delivered', 'Settled']
    ).aggregate(Sum('gallons'))['gallons__sum'] or Decimal('0.0')

    avg_mpg = (
        round(float(total_lifetime_miles) / float(total_stop_gallons), 1)
        if total_stop_gallons > 0
        else 0.0
    )

    # 3. Active settlements (from delivered or active loads)
    active_settlements = actual_trips.aggregate(Sum('payout'))['payout__sum'] or Decimal('0.00')

    context = {
        'trips': all_trips,
        'miles_this_week': miles_this_week,
        'avg_mpg': avg_mpg,
        'active_settlements': active_settlements,
    }
    return render(request, 'tracker/trip_log.html', context)