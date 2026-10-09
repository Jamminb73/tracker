from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User


class DriverProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True)
    llc_name = models.CharField(max_length=150, blank=True)
    truck_number = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - Rig #{self.truck_number}"


class Trip(models.Model):
    STATUS_CHOICES = [
        ('Dispatched', 'Dispatched'),
        ('In Transit', 'In Transit'),
        ('Delivered', 'Delivered'),
        ('Settled', 'Settled'),
    ]

    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trips')
    trip_number = models.CharField(max_length=50, blank=True)
    bol_number = models.CharField(max_length=64, blank=True, verbose_name="BOL #")

    # Financials & Mileage
    payout = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Pay")
    fuel_surcharge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    miles_total = models.DecimalField(max_digits=8, decimal_places=1, default=Decimal('0.0'))

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

    # Customer & Notes
    customer_name = models.CharField(max_length=150, blank=True, db_index=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Delivered')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-pickup_date', '-created_at']

    @property
    def ppm(self):
        """Pay Per Mile: pay / miles (non-editable reporting field)"""
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
        """
        Zach's Formula: Fuel Surcharge - LT (Fuel Total) - DEF - Reefer - CAT Scale
        """
        fuel_total = self.total_fuel_cost
        return (
            (self.fuel_surcharge or Decimal('0.00'))
            - fuel_total
            - (self.def_cost or Decimal('0.00'))
            - (self.reefer_cost or Decimal('0.00'))
            - (self.cat_scale or Decimal('0.00'))
        )

    def __str__(self):
        label = self.bol_number or self.trip_number or 'Trip'
        return f"{label} ({self.origin_city} -> {self.destination_city})"


class FuelStop(models.Model):
    """Sub-table to support 'multiple fuel lines per trip' with the Add Fuel Stop button."""
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='fuel_stops')
    stop_location = models.CharField(max_length=100, blank=True)
    gallons = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'))
    price_per_gallon = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('0.000'))

    @property
    def total_line_cost(self):
        return round(self.gallons * self.price_per_gallon, 2)

    def __str__(self):
        return f"{self.gallons} gal @ ${self.price_per_gallon}/gal"