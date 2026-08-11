from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from apps.box_upload.metadata_jobs import queue_existing_metadata_proposals


class Command(BaseCommand):
    help = "Queue a bounded batch of existing literature for DeepSeek metadata proposals."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--requested-by", default="")
        parser.add_argument("--include-verified", action="store_true")

    def handle(self, *args, **options):
        user = None
        if options["requested_by"]:
            try:
                user = get_user_model().objects.get(username=options["requested_by"], is_staff=True)
            except get_user_model().DoesNotExist as exc:
                raise CommandError("--requested-by must name an existing staff user.") from exc
        result = queue_existing_metadata_proposals(
            requested_by=user,
            limit=options["limit"],
            force=options["include_verified"],
        )
        self.stdout.write(self.style.SUCCESS(f"Queued {result['created']}; reused/skipped {result['reused']}."))
