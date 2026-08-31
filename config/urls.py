from django.urls import include, path
from django.contrib import admin

admin.site.login_template = "accounts/login.html"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("skills/", include("apps.skills.urls")),
    path("", include("apps.box_upload.urls")),
]
