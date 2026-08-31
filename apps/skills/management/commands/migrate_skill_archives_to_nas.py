from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Retired: NJU Box Skill archive migration is no longer available."

    def handle(self, *args, **options):
        raise CommandError("NJU Box Skill archive migration has been retired; all releases must use NAS WebDAV.")
