# NAS Skill 发布包迁移准备

## 配置

在 `.env` 中保留 NAS WebDAV 凭据，并配置：

```dotenv
NAS_WEBDAV_SKILLS_ROOT=/public/PLAB_KnowledgeBase/Skills
SKILL_DOWNLOAD_LINK_MAX_AGE=300
```

旧 ZIP 迁移期间还需要原有 `NJU_BOX_API_TOKEN`、`NJU_SKILLS_REPOSITORY_ID` 和 Skill 库密码。

## 部署与迁移

```powershell
python manage.py migrate
python manage.py migrate_skill_archives_to_nas
# NJU Box 不可连接时：
python manage.py migrate_skill_archives_to_nas --rebuild-from-git
```

迁移命令逐条输出结果。若 NJU Box 或 NAS 暂时不可用，命令以失败状态结束，但失败行仍保持 `nju_box`，恢复连接后可直接重跑。

## 验收查询

```powershell
python manage.py shell -c "from apps.skills.models import SharedSkillRelease as R; print({'nas': R.objects.filter(storage_backend='nas_webdav').count(), 'nju_box': R.objects.filter(storage_backend='nju_box').count()})"
```

完成标准：目标范围内 `nju_box` 为 0，NAS Skills 目录可读取，网页与 MCP 下载返回有效 ZIP。
