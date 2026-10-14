from django.contrib import admin
from .models import DriverProfile, Trip, FuelStop

@admin.register(FeatureSuggestion)
class FeatureSuggestionAdmin(admin.ModelAdmin):
    list_display = ('title', 'user_rig', 'category', 'status', 'created_at')
    list_filter = ('status', 'category', 'created_at')
    search_fields = ('title', 'description', 'admin_notes', 'user__username', 'user__profile__truck_number')
    list_editable = ('status',)
    readonly_fields = ('user', 'category', 'title', 'description', 'created_at')

    def user_rig(self, obj):
        truck = getattr(obj.user.profile, 'truck_number', '') if hasattr(obj.user, 'profile') else ''
        return f"{obj.user.username} (Rig #{truck})" if truck else obj.user.username
    user_rig.short_description = 'Submitted By'


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