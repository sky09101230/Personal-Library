from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import INVALID_INVITATION_MESSAGE, RegistrationForm
from .models import RegistrationInvitation


class _InvitationUnavailable(Exception):
    pass


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
                updated = RegistrationInvitation.available_for(
                    form.cleaned_data["invitation_code"]
                ).update(
                    is_active=False,
                    used_at=timezone.now(),
                    used_by=user,
                )
                if updated != 1:
                    raise _InvitationUnavailable
        except _InvitationUnavailable:
            form.add_error("invitation_code", INVALID_INVITATION_MESSAGE)
        else:
            login(request, user)
            return redirect("home")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("home")
    return render(request, "accounts/login.html", {"form": form})
