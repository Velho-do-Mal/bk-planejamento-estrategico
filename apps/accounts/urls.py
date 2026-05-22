from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/',    views.login_view,   name='login'),
    path('logout/',   views.logout_view,  name='logout'),
    path('registro/', views.registro_view, name='registro'),
    path('usuarios/', views.usuarios_view, name='usuarios'),
]
