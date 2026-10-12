from django.urls import path
from . import views

urlpatterns = [
    path('', views.welcome_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('log/', views.trip_log_view, name='trip_log'),
    path('log/edit/<int:trip_id>/', views.trip_log_view, name='trip_log_edit'),
    path('customer-check/', views.customer_warning_check, name='customer_check'),
]