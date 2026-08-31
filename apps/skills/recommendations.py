from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .github_search import GitHubSearchError, search_github_skills, summarize_github_search_items
from .models import AcademicSkillRecommendation, SkillSyncJob
from .services import InactiveSkillJob, _finish_job, _start_job, _update_job, mark_job_failed


ACADEMIC_SEARCH_TERMS = (
    "academic research",
    "literature review",
    "scientific analysis",
)
MAX_RECOMMENDATION_CANDIDATES = 10


class AcademicRecommendationError(Exception):
    pass


def refresh_academic_recommendations(job=None, search_func=None, summarize_func=None):
    search_func = search_func or search_github_skills
    summarize_func = summarize_func or summarize_github_search_items
    _start_job(job)
    try:
        candidates = {}
        for term in ACADEMIC_SEARCH_TERMS:
            _update_job(job, current_source=f"GitHub: {term}", current_skill="")
            result = search_func(term, page=1)
            for item in result.get("items", []):
                if not item.get("archived") and item.get("full_name") not in candidates:
                    candidates[item["full_name"]] = item
        ranked = sorted(
            candidates.values(),
            key=lambda item: (item.get("stars") or 0, item.get("pushed_at") or ""),
            reverse=True,
        )[:MAX_RECOMMENDATION_CANDIDATES]
        if not ranked:
            raise AcademicRecommendationError("固定学术关键词没有返回可评估的 GitHub Skill。")
        _update_job(job, skills_total=len(ranked), current_source="DeepSeek 学术评估")
        summary_error = summarize_func(ranked)
        if summary_error or any(not item.get("summary") for item in ranked):
            raise AcademicRecommendationError("学术推荐评估未完整完成，已保留上一次结果。")
        selected = [item for item in ranked if item.get("academic_recommended")]
        if not selected:
            raise AcademicRecommendationError("本次没有生成可信的学术推荐，已保留上一次结果。")

        refreshed_at = timezone.now()
        rows = [AcademicSkillRecommendation(
            full_name=item["full_name"],
            skill_path=item["path"],
            recommendation=item["summary"],
            stars=max(0, int(item.get("stars") or 0)),
            repository_pushed_at=parse_datetime(item.get("pushed_at") or ""),
            blob_sha=item["blob_sha"],
            ai_model=item["summary_model"],
            ai_prompt_version=item["summary_prompt_version"],
            refreshed_at=refreshed_at,
        ) for item in selected]
        with transaction.atomic():
            AcademicSkillRecommendation.objects.all().delete()
            AcademicSkillRecommendation.objects.bulk_create(rows)
        _update_job(
            job,
            skills_processed=len(ranked),
            enriched_count=len(rows),
            current_skill="",
        )
        _finish_job(job, SkillSyncJob.COMPLETED)
        return rows
    except (InactiveSkillJob, AcademicRecommendationError, GitHubSearchError):
        raise
    except Exception as exc:
        raise AcademicRecommendationError("生成学术推荐时发生异常，已保留上一次结果。") from exc


def run_academic_recommendation_job(job):
    try:
        return refresh_academic_recommendations(job=job)
    except InactiveSkillJob:
        return []
    except Exception as exc:
        mark_job_failed(job, exc)
        return []
