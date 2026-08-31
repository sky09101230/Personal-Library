# 已废弃：NJU Box Skill 发布包迁移

## 配置

NJU Box 已停用，所有 Skill 发布包均已位于 NAS。迁移命令 `migrate_skill_archives_to_nas` 保留为废弃提示，不能再执行迁移或连接 NJU Box。

NAS 配置仅保留：

```dotenv
NAS_WEBDAV_SKILLS_ROOT=/public/PLAB_KnowledgeBase/Skills
SKILL_DOWNLOAD_LINK_MAX_AGE=300
```

## 验收查询

```powershell
python manage.py shell -c "from apps.skills.models import SharedSkillRelease as R; print({'nas': R.objects.filter(storage_backend='nas_webdav').count()})"
```

完成标准：NAS Skills 目录可读取，网页与 MCP 下载返回有效 ZIP。
