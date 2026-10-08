from django.urls import path
from . import views

urlpatterns = [
    path('', views.welcome_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('log/', views.trip_log_view, name='trip_log'),
]