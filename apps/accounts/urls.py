from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views


urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register, name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
