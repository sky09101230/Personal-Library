from django.urls import path

from . import upload_review, views


urlpatterns = [
    path("", views.home, name="home"),
    path("upload/", upload_review.upload_page, name="box-upload"),
    path("upload/batches/", upload_review.create_batch, name="upload-review-create"),
    path("upload/batches/<int:batch_id>/files/", upload_review.stage_file, name="upload-review-stage-file"),
    path("upload/review-items/<int:item_id>/", upload_review.update_item, name="upload-review-update-item"),
    path("upload/batches/<int:batch_id>/confirm/", upload_review.confirm_batch, name="upload-review-confirm"),
    path("upload/batches/<int:batch_id>/cancel/", upload_review.cancel_batch, name="upload-review-cancel"),
    path("uploads/", views.upload_history, name="upload-history"),
    path("uploads/<int:pk>/delete/", views.delete_upload, name="delete-upload"),
    path("zotero/import/", views.zotero_import, name="zotero-import"),
    path("library/", views.library, name="library"),
    path("library/metadata-review/", views.metadata_review_queue, name="metadata-review-queue"),
    path("library/metadata-review/bulk-accept/", views.metadata_review_bulk_accept, name="metadata-review-bulk-accept"),
    path("library/metadata-review/<int:pk>/", views.metadata_review_detail, name="metadata-review-detail"),
    path("library/metadata-review/<int:pk>/accept/", views.metadata_review_accept, name="metadata-review-accept"),
    path("library/metadata-review/<int:pk>/reject/", views.metadata_review_reject, name="metadata-review-reject"),
    path("library/metadata-review/<int:pk>/regenerate/", views.metadata_review_regenerate, name="metadata-review-regenerate"),
    path("library/<int:document_id>/metadata-review/enqueue/", views.metadata_review_enqueue, name="metadata-review-enqueue"),
    path("library/view/<int:pk>/", views.view_document, name="view-document"),
    path("library/download/<int:pk>/", views.download_document, name="download-document"),
    path("library/download/signed/<str:token>/", views.signed_download_document, name="signed-download-document"),
]
