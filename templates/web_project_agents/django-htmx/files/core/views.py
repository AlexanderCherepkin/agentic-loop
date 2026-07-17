from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods


def home(request):
    return render(request, "core/home.html")


@require_http_methods(["POST"])
def htmx_login(request):
    username = request.POST.get("username")
    password = request.POST.get("password")
    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        return render(request, "core/partials/_user_menu.html", {"user": user})
    return HttpResponse("Invalid credentials", status=401)


@login_required
def htmx_logout(request):
    logout(request)
    return render(request, "core/partials/_guest_menu.html")
