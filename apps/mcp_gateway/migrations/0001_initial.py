from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="McpAccessToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=120)),
                ("token_digest", models.CharField(editable=False, max_length=64, unique=True)),
                ("scopes", models.JSONField(default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mcp_access_tokens", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "MCP 访问令牌",
                "verbose_name_plural": "MCP 访问令牌",
                "ordering": ("-created_at",),
            },
        ),
    ]
