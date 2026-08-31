import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_application = get_asgi_application()

from apps.mcp_gateway.server import application as mcp_application


async def application(scope, receive, send):
    if scope["type"] == "lifespan" or (scope["type"] == "http" and scope.get("path", "").startswith("/mcp")):
        await mcp_application(scope, receive, send)
        return
    await django_application(scope, receive, send)
