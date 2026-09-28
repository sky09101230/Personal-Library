import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from .chat import ChatError
from .evidence import select_active_parse
from .llm import complete
from .models import PaperAnalysisRun
from .skeleton import SkeletonError, generate_skeleton


@login_required
@require_POST
def skeleton_generate(request, document_id):
    body = json.loads(request.body or "{}")
    try:
        parse = select_active_parse(request.user, document_id, parse_id=body.get("parse_id"))
        run = generate_skeleton(parse, request.user, provider=complete, force=bool(body.get("force")),
                                request_id=body.get("request_id"))
    except SkeletonError as exc:
        return JsonResponse({"ok": False, "code": exc.code, "message": str(exc)}, status=400)
    return JsonResponse({"ok": run.status == PaperAnalysisRun.Status.SUCCEEDED, "run_id": run.pk,
                         "status": run.status, "analysis_id": run.result_id, "payload": run.result.payload if run.result_id else None})


@login_required
@require_GET
def skeleton_status(request, run_id):
    run = get_object_or_404(PaperAnalysisRun, pk=run_id, requested_by=request.user)
    return JsonResponse({"run_id": run.pk, "status": run.status, "analysis_id": run.result_id,
                         "error_code": run.error_code, "payload": run.result.payload if run.result_id else None})
