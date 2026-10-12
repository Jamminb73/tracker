from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class DriverProfile(models.Model):
    TIER_CHOICES = [
        ('BETA_LIFETIME', 'Beta VIP (Lifetime Free)'),
        ('ACTIVE_PAID', 'Active Paid Subscriber'),
        ('TRIAL', 'Free Trial'),
        ('EXPIRED', 'Subscription Expired'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True)
    llc_name = models.CharField(max_length=150, blank=True)
    truck_number = models.CharField(max_length=50)

    # Subscription / Access Management
    tier = models.CharField(max_length=30, choices=TIER_CHOICES, default='BETA_LIFETIME')
    subscription_end_date = models.DateField(null=True, blank=True)

    @property
    def has_access(self):
        """Single source of truth for paywall gating."""
        if self.user.is_superuser or self.user.is_staff:
            return True
        if self.tier in ['BETA_LIFETIME', 'ACTIVE_PAID']:
            return True
        if self.tier == 'TRIAL' and self.subscription_end_date:
            return timezone.now().date() <= self.subscription_end_date
        return False

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - Rig #{self.truck_number} ({self.get_tier_display()})"


class Trip(models.Model):
    STATUS_CHOICES = [
        ('Quote / Planner', 'Quote / Mission Planner'),
        ('Booked', 'Booked / Scheduled'),
        ('Dispatched', 'Dispatched'),
        ('In Transit', 'In Transit'),
        ('Delivered', 'Delivered'),
        ('Settled', 'Settled'),
    ]

    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trips')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Delivered')

    trip_number = models.CharField(max_length=50, blank=True)
    bol_number = models.CharField(max_length=64, blank=True, verbose_name="BOL #")

    # Financials & Mileage
    payout = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Pay ($)")
    fuel_surcharge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Fuel Surcharge ($)")

    # Primary driver input: Total odometer / routed miles
    miles_total = models.DecimalField(max_digits=8, decimal_places=1, default=Decimal('0.0'), verbose_name="Total Miles")

    # Optional inputs for drivers who want granular breakdowns
    loaded_miles = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True, verbose_name="Loaded Miles (Optional)")
    deadhead_miles = models.DecimalField(max_digits=8, decimal_places=1, default=Decimal('0.0'), blank=True, verbose_name="Deadhead Miles (Optional)")

    # Origin & Pickup
    origin_city = models.CharField(max_length=100)
    pickup_date = models.DateField(null=True, blank=True)
    pickup_arrival = models.TimeField(null=True, blank=True)
    pickup_departure = models.TimeField(null=True, blank=True)

    # Legacy / Single Quick-Log Fuel (fallback if not using multi-line fuel stops)
    fuel_gallons = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    fuel_cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Price Per Gallon")

    # Surcharge deductions & trip expenses
    def_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name="DEF")
    reefer_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name="Reefer")
    cat_scale = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name="CAT Scale")
    incidentals = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))

    # Destination & Delivery
    destination_city = models.CharField(max_length=100)
    destination_date = models.DateField(null=True, blank=True, verbose_name="Delivery Date")
    destination_arrival = models.TimeField(null=True, blank=True)
    destination_departure = models.TimeField(null=True, blank=True)

    # Customer & Private Driver Notes
    customer_name = models.CharField(max_length=150, blank=True, db_index=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-pickup_date', '-created_at']

    # --- Core Mileage & Revenue Calculations ---
    @property
    def all_miles(self):
        """Total odometer miles required."""
        return self.miles_total or Decimal('0.0')

    @property
    def gross_revenue(self):
        """Total pay plus fuel surcharge."""
        return (self.payout or Decimal('0.00')) + (self.fuel_surcharge or Decimal('0.00'))

    @property
    def ppm(self):
        """Gross Rate Per Mile: Pay / Total Miles."""
        if self.miles_total and self.miles_total > 0:
            return round(self.payout / self.miles_total, 2)
        return Decimal('0.00')

    @property
    def total_fuel_cost(self):
        """Calculates total fuel expense across multiple fuel lines, or falls back to quick-log."""
        stops = self.fuel_stops.all()
        if stops.exists():
            return sum((stop.gallons * stop.price_per_gallon for stop in stops), Decimal('0.00'))
        if self.fuel_gallons and self.fuel_cost:
            return round(self.fuel_gallons * self.fuel_cost, 2)
        return Decimal('0.00')

    @property
    def running_total(self):
        """Zach's Formula: Fuel Surcharge - LT (Fuel Total) - DEF - Reefer - CAT Scale."""
        return (
            (self.fuel_surcharge or Decimal('0.00'))
            - self.total_fuel_cost
            - (self.def_cost or Decimal('0.00'))
            - (self.reefer_cost or Decimal('0.00'))
            - (self.cat_scale or Decimal('0.00'))
        )

    # --- Mission Planner / Risk vs. Reward Metrics ---
    @property
    def total_expenses(self):
        """All out-of-pocket costs on this load."""
        return (
            self.total_fuel_cost
            + (self.def_cost or Decimal('0.00'))
            + (self.reefer_cost or Decimal('0.00'))
            + (self.cat_scale or Decimal('0.00'))
            + (self.incidentals or Decimal('0.00'))
        )

    @property
    def net_profit(self):
        """True money left after diesel and road expenses."""
        return self.gross_revenue - self.total_expenses

    @property
    def net_ppm(self):
        """True take-home per mile driven."""
        if self.miles_total and self.miles_total > 0:
            return round(self.net_profit / self.miles_total, 2)
        return Decimal('0.00')

    def save(self, *args, **kwargs):
        # Auto-fill loaded miles if omitted
        if not self.loaded_miles and self.miles_total:
            self.loaded_miles = max(Decimal('0.0'), self.miles_total - (self.deadhead_miles or Decimal('0.0')))
        super().save(*args, **kwargs)

    def __str__(self):
        label = self.bol_number or self.trip_number or 'Trip'
        return f"{label} ({self.origin_city} -> {self.destination_city})"


class FuelStop(models.Model):
    """Sub-table to support multiple fuel lines per trip."""
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='fuel_stops')
    stop_location = models.CharField(max_length=100, blank=True)
    gallons = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'))
    price_per_gallon = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('0.000'))

    @property
    def total_line_cost(self):
        return round(self.gallons * self.price_per_gallon, 2)

    def __str__(self):
        return f"{self.gallons} gal @ ${self.price_per_gallon}/gal"


class CustomerReview(models.Model):
    """Crowdsourced shipper / receiver intel shared between drivers."""
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_reviews')
    customer_name = models.CharField(max_length=150, db_index=True)
    comment = models.TextField()
    
    # Quick facility flags drivers care most about
    overnight_parking = models.BooleanField(default=False, verbose_name="Overnight Parking Available")
    heavy_detention = models.BooleanField(default=False, verbose_name="Long Detention (3+ hrs)")
    rating = models.PositiveSmallIntegerField(default=5)  # 1 to 5 stars
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        truck = getattr(self.author.profile, 'truck_number', '') if hasattr(self.author, 'profile') else ''
        author_label = f"Rig #{truck}" if truck else self.author.username
        return f"{self.customer_name} ({self.rating}★) by {author_label}"