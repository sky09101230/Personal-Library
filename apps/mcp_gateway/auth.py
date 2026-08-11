from asgiref.sync import sync_to_async
from django.utils import timezone
from mcp.server.auth.provider import AccessToken

from .models import McpAccessToken


class DatabaseTokenVerifier:
    async def verify_token(self, token):
        record = await sync_to_async(self._find_valid_token, thread_sensitive=True)(token)
        if record is None:
            return None
        return AccessToken(
            token=token,
            client_id=f"user:{record.owner_id}",
            scopes=record.scopes,
            expires_at=int(record.expires_at.timestamp()) if record.expires_at else None,
        )

    @staticmethod
    def _find_valid_token(token):
        record = McpAccessToken.objects.filter(
            token_digest=McpAccessToken.digest(token),
            is_active=True,
        ).select_related("owner").first()
        if record is None or (record.expires_at and record.expires_at <= timezone.now()):
            return None
        record.last_used_at = timezone.now()
        record.save(update_fields=["last_used_at"])
        return record
