from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("htmx/login/", views.htmx_login, name="htmx_login"),
    path("htmx/logout/", views.htmx_logout, name="htmx_logout"),
]
