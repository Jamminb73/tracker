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

    DRIVER_TYPE_CHOICES = [
        ('OWNER_OPERATOR', 'Owner-Operator / Lease'),
        ('COMPANY', 'Company Driver'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True)
    llc_name = models.CharField(max_length=150, blank=True)
    truck_number = models.CharField(max_length=50)

    # Driver Logging Defaults
    default_driver_type = models.CharField(
        max_length=20,
        choices=DRIVER_TYPE_CHOICES,
        default='OWNER_OPERATOR',
        verbose_name="Default Logging Mode"
    )
    default_cpm = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Default CPM ($/mi)"
    )

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

    @property
    def is_editable(self):
        """Locked once Delivered or Settled."""
        return self.status not in ['Delivered', 'Settled']
    
    STATUS_CHOICES = [
        ('Quote / Planner', 'Quote / Mission Planner'),
        ('Booked', 'Booked / Scheduled'),
        ('Dispatched', 'Dispatched'),
        ('In Transit', 'In Transit'),
        ('Delivered', 'Delivered'),
        ('Settled', 'Settled'),
    ]

    DRIVER_MODE_CHOICES = [
        ('OWNER_OPERATOR', 'Owner-Operator / Lease'),
        ('COMPANY', 'Company Driver'),
    ]

    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trips')
    driver_mode = models.CharField(
        max_length=20,
        choices=DRIVER_MODE_CHOICES,
        default='OWNER_OPERATOR',
        verbose_name="Driver Mode"
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Delivered')

    trip_number = models.CharField(max_length=50, blank=True)
    bol_number = models.CharField(max_length=64, blank=True, verbose_name="BOL #")

    # Financials & Mileage
    payout = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Pay ($)")
    cpm_rate = models.DecimalField(max_digits=5, decimal_places=3, null=True, blank=True, verbose_name="Cents Per Mile ($)")
    fuel_surcharge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Fuel Surcharge ($)")

    # Primary driver input: Total odometer / routed miles
    miles_total = models.DecimalField(max_digits=8, decimal_places=1, default=Decimal('0.0'), verbose_name="Total Miles")

    # Optional inputs for drivers who want granular breakdowns
    loaded_miles = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True, verbose_name="Loaded Miles (Optional)")
    deadhead_miles = models.DecimalField(max_digits=8, decimal_places=1, default=Decimal('0.0'), blank=True, verbose_name="Deadhead Miles (Optional)")

    # Origin & Pickup (Shipper)
    origin_city = models.CharField(max_length=100)
    pickup_facility = models.CharField(max_length=150, blank=True, db_index=True, verbose_name="Shipper / Pickup Facility")
    pickup_date = models.DateField(null=True, blank=True)
    pickup_arrival = models.TimeField(null=True, blank=True)
    pickup_departure = models.TimeField(null=True, blank=True)
    pickup_notes = models.TextField(blank=True, verbose_name="Pickup / Shipper Notes")

    # Legacy / Single Quick-Log Fuel (fallback if not using multi-line fuel stops)
    fuel_gallons = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    fuel_cost = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True, verbose_name="Price Per Gallon")

    # Surcharge deductions & trip expenses
    def_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name="DEF")
    reefer_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name="Reefer")
    cat_scale = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name="CAT Scale")
    tolls = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name="Tolls ($)")
    incidentals = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))

    # Destination & Delivery (Receiver)
    destination_city = models.CharField(max_length=100)
    destination_facility = models.CharField(max_length=150, blank=True, db_index=True, verbose_name="Receiver / Delivery Facility")
    destination_date = models.DateField(null=True, blank=True, verbose_name="Delivery Date")
    destination_arrival = models.TimeField(null=True, blank=True)
    destination_departure = models.TimeField(null=True, blank=True)
    delivery_notes = models.TextField(blank=True, verbose_name="Delivery / Receiver Notes")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-pickup_date', '-created_at']

    # --- Backwards Compatibility Bridge ---
    @property
    def customer_name(self):
        """Returns receiver facility, pickup facility, or empty string."""
        if self.destination_facility and self.pickup_facility:
            return f"{self.pickup_facility} -> {self.destination_facility}"
        return self.destination_facility or self.pickup_facility or ""

    @customer_name.setter
    def customer_name(self, value):
        self.destination_facility = value

    @property
    def notes(self):
        """Combines pickup and delivery notes if both exist."""
        notes = []
        if self.pickup_notes:
            notes.append(f"[Pickup]: {self.pickup_notes}")
        if self.delivery_notes:
            notes.append(f"[Drop]: {self.delivery_notes}")
        return " | ".join(notes)

    @notes.setter
    def notes(self, value):
        self.delivery_notes = value

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
        """Gross Rate Per Mile: Pay / Total Miles (or directly the CPM in company mode)."""
        if self.driver_mode == 'COMPANY' and self.cpm_rate:
            return round(self.cpm_rate, 2)
        if self.miles_total and self.miles_total > 0:
            return round(self.payout / self.miles_total, 2)
        return Decimal('0.00')

    @property
    def total_fuel_cost(self):
        """Calculates total fuel expense across multiple fuel lines, or falls back to quick-log."""
        if self.driver_mode == 'COMPANY':
            return Decimal('0.00')
        stops = self.fuel_stops.all()
        if stops.exists():
            return sum((stop.gallons * stop.price_per_gallon for stop in stops), Decimal('0.00'))
        if self.fuel_gallons and self.fuel_cost:
            return round(self.fuel_gallons * self.fuel_cost, 2)
        return Decimal('0.00')

    @property
    def running_total(self):
        """Zach's Formula: Fuel Surcharge - LT (Fuel Total) - DEF - Reefer - CAT Scale - Tolls."""
        if self.driver_mode == 'COMPANY':
            return Decimal('0.00')
        return (
            (self.fuel_surcharge or Decimal('0.00'))
            - self.total_fuel_cost
            - (self.def_cost or Decimal('0.00'))
            - (self.reefer_cost or Decimal('0.00'))
            - (self.cat_scale or Decimal('0.00'))
            - (self.tolls or Decimal('0.00'))
        )

    # --- Mission Planner / Risk vs. Reward Metrics ---
    @property
    def total_expenses(self):
        """All out-of-pocket costs on this load."""
        if self.driver_mode == 'COMPANY':
            return Decimal('0.00')
        return (
            self.total_fuel_cost
            + (self.def_cost or Decimal('0.00'))
            + (self.reefer_cost or Decimal('0.00'))
            + (self.cat_scale or Decimal('0.00'))
            + (self.tolls or Decimal('0.00'))
            + (self.incidentals or Decimal('0.00'))
        )

    @property
    def net_profit(self):
        """True money left after diesel and road expenses."""
        if self.driver_mode == 'COMPANY':
            return self.payout or Decimal('0.00')
        return self.gross_revenue - self.total_expenses

    @property
    def net_ppm(self):
        """True take-home per mile driven."""
        if self.driver_mode == 'COMPANY' and self.cpm_rate:
            return round(self.cpm_rate, 2)
        if self.miles_total and self.miles_total > 0:
            return round(self.net_profit / self.miles_total, 2)
        return Decimal('0.00')

    def save(self, *args, **kwargs):
        # In Company Mode: If payout is 0/empty, auto-calculate pay = miles * cpm
        if self.driver_mode == 'COMPANY' and self.cpm_rate and self.miles_total:
            if not self.payout or self.payout == Decimal('0.00'):
                self.payout = round(self.miles_total * self.cpm_rate, 2)

        # Auto-fill loaded miles if omitted
        if not self.loaded_miles and self.miles_total:
            self.loaded_miles = max(Decimal('0.0'), self.miles_total - (self.deadhead_miles or Decimal('0.0')))
            
        super().save(*args, **kwargs)

    def __str__(self):
        label = self.bol_number or self.trip_number or 'Trip'
        origin = f"{self.pickup_facility} ({self.origin_city})" if self.pickup_facility else self.origin_city
        destination = f"{self.destination_facility} ({self.destination_city})" if self.destination_facility else self.destination_city
        return f"{label} [{origin} -> {destination}]"


class FuelStop(models.Model):
    """Sub-table to support multiple fuel lines per trip."""
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='fuel_stops')
    stop_location = models.CharField(max_length=100, blank=True)
    gallons = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal('0.000'))
    price_per_gallon = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('0.000'))

    @property
    def total_line_cost(self):
        return round(self.gallons * self.price_per_gallon, 2)

    def __str__(self):
        return f"{self.gallons} gal @ ${self.price_per_gallon}/gal"


class CustomerReview(models.Model):
    """Crowdsourced shipper / receiver intel shared between drivers."""
    FACILITY_TYPE_CHOICES = [
        ('PICKUP', 'Shipper / Pickup Facility'),
        ('DELIVERY', 'Receiver / Delivery Facility'),
        ('GENERAL', 'General Facility'),
    ]

    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_reviews')
    facility_type = models.CharField(max_length=15, choices=FACILITY_TYPE_CHOICES, default='GENERAL')
    customer_name = models.CharField(max_length=150, db_index=True, verbose_name="Facility Name")
    comment = models.TextField()
    
    # Facility flags
    overnight_parking = models.BooleanField(default=False, verbose_name="Overnight Parking Available")
    heavy_detention = models.BooleanField(default=False, verbose_name="Long Detention (3+ hrs)")
    rating = models.PositiveSmallIntegerField(default=5)  # 1 to 5 stars
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        truck = getattr(self.author.profile, 'truck_number', '') if hasattr(self.author, 'profile') else ''
        author_label = f"Rig #{truck}" if truck else self.author.username
        return f"[{self.get_facility_type_display()}] {self.customer_name} ({self.rating}★) by {author_label}"


class FeatureSuggestion(models.Model):
    """Driver ideas and feature requests routed to Django Admin."""
    CATEGORY_CHOICES = [
        ('FEATURE', 'New Feature Idea'),
        ('EXPENSE', 'New Expense / Calculation Field'),
        ('BUG', 'Bug / Glitch Report'),
        ('OTHER', 'General Suggestion'),
    ]

    STATUS_CHOICES = [
        ('NEW', 'New / Under Review'),
        ('PLANNED', 'Planned / In Roadmap'),
        ('IN_PROGRESS', 'Currently Building'),
        ('COMPLETED', 'Completed / Released'),
        ('DECLINED', 'Declined'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='suggestions')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='FEATURE')
    title = models.CharField(max_length=150, verbose_name="Summary / Title")
    description = models.TextField(verbose_name="Details / What would help you?")
    
    # Internal dev tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW')
    admin_notes = models.TextField(blank=True, verbose_name="Internal Developer Notes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        truck = getattr(self.user.profile, 'truck_number', '') if hasattr(self.user, 'profile') else ''
        author = f"Rig #{truck}" if truck else self.user.username
        return f"[{self.get_status_display()}] {self.title} - {author}"