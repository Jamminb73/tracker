from django.db import models
from django.contrib.auth.models import User

# Extends the standard Django User with driver & rig info
class DriverProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True)
    llc_name = models.CharField(max_length=150, blank=True)
    truck_number = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - Rig #{self.truck_number}"

# The core trip log model
class Trip(models.Model):
    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trips')
    trip_number = models.CharField(max_length=50)
    payout = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    miles = models.DecimalField(max_digits=8, decimal_places=1, default=0.0)
    fuel_surcharge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Route
    origin_city = models.CharField(max_length=100)
    destination_city = models.CharField(max_length=100)
    
    # Timing
    pickup_date = models.DateField(null=True, blank=True)
    pickup_arrival = models.TimeField(null=True, blank=True)
    pickup_departure = models.TimeField(null=True, blank=True)
    
    destination_date = models.DateField(null=True, blank=True)
    destination_arrival = models.TimeField(null=True, blank=True)
    destination_departure = models.TimeField(null=True, blank=True)

    # Miscellaneous Expenses
    tolls = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    incidentals = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Trip #{self.trip_number} ({self.origin_city} -> {self.destination_city})"

# Flexible expense items (Fuel, DEF, Reefer) attached to a trip
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