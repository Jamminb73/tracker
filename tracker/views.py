import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.utils import timezone
from .models import DriverProfile, Trip, FuelStop, CustomerReview


def _parse_decimal(val, default='0.00'):
    """Helper to safely parse form decimals without crashing on empty strings."""
    if val is None or str(val).strip() == '':
        return Decimal(default) if default is not None else None
    try:
        return Decimal(str(val).strip())
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default) if default is not None else None


def welcome_view(request):
    if request.user.is_authenticated:
        return redirect('trip_log')
    return render(request, 'tracker/welcome.html')


def register_view(request):
    if request.method == 'POST':
        # --- Bot Traps ---
        if request.POST.get('website_url'):
            return redirect('login')

        load_time = request.POST.get('form_load_time')
        if load_time:
            try:
                duration_seconds = (time.time() * 1000 - float(load_time)) / 1000
                if duration_seconds < 2.0:
                    return redirect('login')
            except (ValueError, TypeError):
                return redirect('login')
        # -----------------

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
        login_input = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        matched_user = User.objects.filter(
            Q(username__iexact=login_input) | Q(email__iexact=login_input)
        ).first()

        auth_username = matched_user.username if matched_user else login_input
        user = authenticate(request, username=auth_username, password=password)

        if user is not None:
            login(request, user)
            return redirect('trip_log')
        else:
            error = 'Invalid email/username or password.'

    return render(request, 'tracker/login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required(login_url='login')
def customer_warning_check(request):
    """Endpoint for instant lookup of prior driver notes and shared community intel."""
    query = request.GET.get('name', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'warnings': [], 'community_reviews': []})

    # 1. Driver's own private load notes
    personal_notes = (
        Trip.objects.filter(driver=request.user, customer_name__icontains=query)
        .exclude(notes__exact='')
        .order_by('-pickup_date')[:3]
    )

    red_flags = ['pain', 'trouble', 'avoid', 'slow', 'detention', 'bad', 'refused', 'waste', 'late', 'dock']
    warnings = []

    for trip in personal_notes:
        note_lower = trip.notes.lower()
        is_red_flag = any(flag in note_lower for flag in red_flags)
        warnings.append({
            'date': trip.pickup_date.strftime('%b %d, %Y') if trip.pickup_date else 'Past Trip',
            'trip_number': trip.trip_number or trip.bol_number or 'N/A',
            'notes': trip.notes,
            'is_red_flag': is_red_flag,
        })

    # 2. Crowdsourced reviews from other drivers for this facility
    community_feed = []
    reviews = (
        CustomerReview.objects.filter(customer_name__icontains=query)
        .select_related('author__profile')
        .order_by('-created_at')[:5]
    )

    for rev in reviews:
        truck = getattr(rev.author.profile, 'truck_number', '') if hasattr(rev.author, 'profile') else ''
        author_tag = f"Rig #{truck}" if truck else "Verified Driver"
        community_feed.append({
            'driver_tag': author_tag,
            'rating': rev.rating,
            'comment': rev.comment,
            'overnight_parking': rev.overnight_parking,
            'heavy_detention': rev.heavy_detention,
            'date': rev.created_at.strftime('%b %d, %Y')
        })

    return JsonResponse({
        'warnings': warnings,
        'community_reviews': community_feed
    })


@login_required(login_url='login')
def trip_log_view(request, trip_id=None):
    profile = getattr(request.user, 'profile', None)

    # 1. Resolve existing trip if editing via URL
    active_trip = None
    if trip_id:
        active_trip = get_object_or_404(Trip, id=trip_id, driver=request.user)

    if request.method == 'POST':
        # Check if an existing trip ID came through hidden input or URL
        post_trip_id = request.POST.get('trip_id') or trip_id
        if post_trip_id:
            trip = get_object_or_404(Trip, id=post_trip_id, driver=request.user)
        else:
            trip = Trip(driver=request.user)

        driver_mode = request.POST.get('driver_mode', 'OWNER_OPERATOR')
        trip_number = request.POST.get('trip_number', '').strip()
        bol_number = request.POST.get('bol_number', '').strip()

        # Mileage Parsing & Intelligent Fallback
        raw_total_miles = _parse_decimal(request.POST.get('miles_total'), default=None)
        raw_loaded_miles = _parse_decimal(request.POST.get('loaded_miles'), default=None)
        deadhead_miles = _parse_decimal(request.POST.get('deadhead_miles'), default='0.0')

        if raw_total_miles is not None:
            miles_total = raw_total_miles
            loaded_miles = raw_loaded_miles if raw_loaded_miles is not None else max(Decimal('0.0'), miles_total - deadhead_miles)
        elif raw_loaded_miles is not None:
            loaded_miles = raw_loaded_miles
            miles_total = loaded_miles + deadhead_miles
        else:
            miles_total = Decimal('0.0')
            loaded_miles = Decimal('0.0')

        cpm_rate = _parse_decimal(request.POST.get('cpm_rate'), default=None)

        # Revenue & Mode Calculations
        if driver_mode == 'COMPANY':
            posted_pay = _parse_decimal(request.POST.get('payout'), default=None)
            if posted_pay is not None and posted_pay > Decimal('0.00'):
                payout = posted_pay
            elif cpm_rate and miles_total:
                payout = round(miles_total * cpm_rate, 2)
            else:
                payout = Decimal('0.00')

            fuel_surcharge = Decimal('0.00')
            cat_scale = Decimal('0.00')
            incidentals = Decimal('0.00')
        else:
            payout = _parse_decimal(request.POST.get('payout'), default='0.00')
            fuel_surcharge = _parse_decimal(request.POST.get('fuel_surcharge'), default='0.00')
            cat_scale = _parse_decimal(request.POST.get('cat_scale'), default='0.00')
            incidentals = _parse_decimal(request.POST.get('incidentals'), default='0.00')

        # Always aggregate DEF & Reefer regardless of driver mode
        def_entries = request.POST.getlist('def_cost_entry[]')
        if def_entries:
            def_cost = sum(_parse_decimal(c, default='0.00') for c in def_entries)
        else:
            def_cost = _parse_decimal(request.POST.get('def_cost'), default='0.00')

        reefer_entries = request.POST.getlist('reefer_cost_entry[]')
        if reefer_entries:
            reefer_cost = sum(_parse_decimal(r, default='0.00') for r in reefer_entries)
        else:
            reefer_cost = _parse_decimal(request.POST.get('reefer_cost'), default='0.00')

        # Origin & Pickup
        origin_city = request.POST.get('origin_city', '').strip()
        pickup_date = request.POST.get('pickup_date') or None
        pickup_arrival = request.POST.get('pickup_arrival') or None
        pickup_departure = request.POST.get('pickup_departure') or None

        # Destination & Delivery
        destination_city = request.POST.get('destination_city', '').strip()
        destination_date = request.POST.get('destination_date') or request.POST.get('delivery_date') or None
        destination_arrival = request.POST.get('destination_arrival') or None
        destination_departure = request.POST.get('destination_departure') or None

        # Customer & Private Notes
        customer_name = request.POST.get('customer_name', '').strip()
        notes = request.POST.get('notes', '').strip()

        # Status transition by submit button clicked:
        action = request.POST.get('action', '')
        if 'plan_mission' in request.POST or action in ['plan_mission', 'quote']:
            status = 'Quote / Planner'
        elif 'complete_trip' in request.POST or action == 'complete_trip':
            status = 'Delivered'
        else:
            # "Save Daily Log"
            status = 'In Transit' if trip.status in ['Quote / Planner', None, ''] else trip.status

        # Update Trip instance
        trip.driver_mode = driver_mode
        trip.trip_number = trip_number
        trip.bol_number = bol_number
        trip.payout = payout
        trip.cpm_rate = cpm_rate
        trip.fuel_surcharge = fuel_surcharge
        trip.miles_total = miles_total
        trip.loaded_miles = loaded_miles
        trip.deadhead_miles = deadhead_miles
        trip.origin_city = origin_city
        trip.pickup_date = pickup_date
        trip.pickup_arrival = pickup_arrival
        trip.pickup_departure = pickup_departure
        trip.def_cost = def_cost
        trip.reefer_cost = reefer_cost
        trip.cat_scale = cat_scale
        trip.incidentals = incidentals
        trip.destination_city = destination_city
        trip.destination_date = destination_date
        trip.destination_arrival = destination_arrival
        trip.destination_departure = destination_departure
        trip.customer_name = customer_name
        trip.notes = notes
        trip.status = status
        trip.save()

        # Sync Fuel Stops for all driver modes (keeps diesel history for both Company and Owner-Op)
        trip.fuel_stops.all().delete()
        locations = request.POST.getlist('stop_location[]') or request.POST.getlist('fuel_location[]')
        gallons_list = request.POST.getlist('fuel_gallons[]')
        prices_list = request.POST.getlist('fuel_price[]')

        for loc, gal, price in zip(locations, gallons_list, prices_list):
            if gal and price:
                try:
                    FuelStop.objects.create(
                        trip=trip,
                        stop_location=loc.strip(),
                        gallons=Decimal(str(gal).strip()),
                        price_per_gallon=Decimal(str(price).strip())
                    )
                except (InvalidOperation, ValueError, TypeError):
                    pass

        # Optional: Save/Update shared community review
        if request.POST.get('share_review') and customer_name and notes:
            rating = int(request.POST.get('review_rating', 5))
            overnight_parking = request.POST.get('review_parking') == 'on' or request.POST.get('overnight_parking') == 'on'
            heavy_detention = request.POST.get('review_detention') == 'on' or request.POST.get('heavy_detention') == 'on'

            CustomerReview.objects.update_or_create(
                author=request.user,
                customer_name=customer_name,
                defaults={
                    'comment': notes,
                    'rating': rating,
                    'overnight_parking': overnight_parking,
                    'heavy_detention': heavy_detention,
                }
            )

        if status == 'Delivered':
            messages.success(request, f"Trip #{trip.trip_number or trip.id} completed & delivered!")
        elif post_trip_id:
            messages.success(request, f"Trip #{trip.trip_number or trip.id} updated successfully.")
        else:
            messages.success(request, "New trip logged successfully.")

        return redirect('trip_log')

    # Query trips for history table
    all_trips = Trip.objects.filter(driver=request.user).prefetch_related('fuel_stops').order_by('-created_at')
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

    # 2. Avg fuel efficiency (counts all delivered/in-transit trips with fuel recorded)
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

    # 3. Active settlements
    active_settlements = actual_trips.aggregate(Sum('payout'))['payout__sum'] or Decimal('0.00')

    # Profile defaults
    default_driver_mode = getattr(profile, 'default_driver_type', 'OWNER_OPERATOR') if profile else 'OWNER_OPERATOR'
    default_cpm = getattr(profile, 'default_cpm', None) if profile else None

    context = {
        'active_trip': active_trip,
        'trips': all_trips,
        'miles_this_week': miles_this_week,
        'avg_mpg': avg_mpg,
        'active_settlements': active_settlements,
        'default_driver_mode': default_driver_mode,
        'default_cpm': default_cpm or '',
    }
    return render(request, 'tracker/trip_log.html', context)