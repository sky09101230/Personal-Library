from django.urls import path

from . import views


urlpatterns = [
    path("", views.index, name="skills-index"),
    path("my/", views.my_skills, name="skills-library"),
    path("featured/", views.featured, name="skills-featured"),
    path("discover/github/", views.discover_github, name="skills-discover-github"),
    path("discover/github/import/", views.import_github_candidate, name="skills-import-github"),
    path("discover/academic/", views.academic_recommendations, name="skills-academic-recommendations"),
    path("discover/academic/refresh/", views.refresh_academic_recommendations, name="skills-refresh-academic-recommendations"),
    path("submit/", views.submit_candidate, name="skills-submit-candidate"),
    path("candidates/", views.candidates, name="skills-candidates"),
    path("candidates/publish/", views.batch_publish_candidates, name="skills-candidates-batch-publish"),
    path("candidates/<int:candidate_id>/", views.candidate_detail, name="skills-candidate-detail"),
    path("candidates/<int:candidate_id>/review/", views.review_candidate, name="skills-candidate-review"),
    path("install/<int:skill_id>/", views.install, name="skills-install"),
    path("install/<int:skill_id>/remove/", views.uninstall, name="skills-uninstall"),
    path("install/<int:skill_id>/enabled/", views.set_enabled, name="skills-set-enabled"),
    path("sync/", views.sync, name="skills-sync"),
    path("enrich/", views.enrich, name="skills-enrich"),
    path("sync/<int:job_id>/status/", views.sync_status, name="skills-sync-status"),
    path("download/<str:token>/", views.signed_download, name="signed-download-skill"),
    path("<slug:source_slug>/<slug:slug>/description/", views.edit_description, name="skills-source-description-edit"),
    path("<slug:source_slug>/<slug:slug>/download/", views.download, name="skills-source-download"),
    path("<slug:slug>/download/", views.download, name="skills-download"),
    path("<slug:source_slug>/<slug:slug>/", views.detail, name="skills-source-detail"),
    path("<slug:slug>/", views.detail, name="skills-detail"),
]
