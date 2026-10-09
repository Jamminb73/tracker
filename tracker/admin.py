from django.contrib import admin
from .models import DriverProfile, Trip, FuelStop


class FuelStopInline(admin.TabularInline):
    model = FuelStop
    extra = 1


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'truck_number', 'tier', 'subscription_end_date', 'has_access')
    list_filter = ('tier',)
    search_fields = ('user__username', 'user__email', 'truck_number', 'llc_name')


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('trip_number', 'bol_number', 'driver', 'status', 'pickup_date', 'payout', 'running_total')
    list_filter = ('status', 'pickup_date')
    search_fields = ('trip_number', 'bol_number', 'customer_name', 'driver__username')
    inlines = [FuelStopInline]