from django.urls import path

from . import views


urlpatterns = [
    path("<int:document_id>/", views.literature_detail, name="literature-detail"),
]

