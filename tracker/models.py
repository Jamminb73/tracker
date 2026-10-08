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
    trip_date = models.DateField(null=True, blank=True)
    trip_number = models.CharField(max_length=50, blank=True)
    bol_number = models.CharField(max_length=64, blank=True)

    # Route
    origin_city = models.CharField(max_length=100)
    destination_city = models.CharField(max_length=100)

    # Odometers & Mileage
    start_odometer = models.DecimalField(max_digits=10, decimal_places=1, default=0.0)
    end_odometer = models.DecimalField(max_digits=10, decimal_places=1, default=0.0)
    miles = models.DecimalField(max_digits=8, decimal_places=1, default=0.0)

    # Financials & Settlements
    payout = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fuel_surcharge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Daily Fuel Quick Log
    fuel_gallons = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    fuel_cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Timing
    pickup_date = models.DateField(null=True, blank=True)
    pickup_arrival = models.TimeField(null=True, blank=True)
    pickup_departure = models.TimeField(null=True, blank=True)

    destination_date = models.DateField(null=True, blank=True)
    destination_arrival = models.TimeField(null=True, blank=True)
    destination_departure = models.TimeField(null=True, blank=True)

    # Miscellaneous Expenses & Notes
    tolls = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    incidentals = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Delivered')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-trip_date', '-created_at']

    @property
    def total_miles(self):
        """Returns calculated miles from odometer splits, or falls back to self.miles."""
        if self.end_odometer and self.start_odometer and self.end_odometer > self.start_odometer:
            return round(self.end_odometer - self.start_odometer, 1)
        return self.miles

    def save(self, *args, **kwargs):
        # Auto-compute miles from odometers if provided
        if self.end_odometer and self.start_odometer and self.end_odometer > self.start_odometer:
            self.miles = self.end_odometer - self.start_odometer
        super().save(*args, **kwargs)

    def __str__(self):
        label = self.bol_number or self.trip_number or 'Trip'
        return f"{label} ({self.origin_city} -> {self.destination_city})"


class FuelExpense(models.Model):
    FUEL_CHOICES = [
        ('DIESEL', 'Diesel'),
        ('DEF', 'DEF'),
        ('REEFER', 'Reefer'),
    ]
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='fuel_entries')
    fuel_type = models.CharField(max_length=10, choices=FUEL_CHOICES, default='DIESEL')
    gallons = models.DecimalField(max_digits=7, decimal_places=2, default=0.00)
    cost = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    receipt_image = models.ImageField(upload_to='receipts/', null=True, blank=True)

    def __str__(self):
        return f"{self.fuel_type} - ${self.cost} ({self.gallons} gal)"