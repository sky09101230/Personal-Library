from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .evidence import EvidenceError, build_catalog, select_active_parse
from .evidence_assets import read_figure_asset


@login_required
@require_GET
def evidence_detail(request, document_id, parse_id, evidence_id):
    try:
        parse = select_active_parse(request.user, document_id, parse_id=parse_id)
        evidence = build_catalog(parse).get(evidence_id)
    except EvidenceError as exc:
        return JsonResponse({"ok": False, "code": exc.code, "message": str(exc)}, status=404)
    return JsonResponse({"ok": True, "evidence": evidence.as_dict()})


@login_required
@require_GET
def figure_asset(request, document_id, parse_id, evidence_id):
    try:
        parse = select_active_parse(request.user, document_id, parse_id=parse_id)
        evidence = build_catalog(parse).get(evidence_id)
        mime, data = read_figure_asset(parse, evidence)
    except EvidenceError:
        return HttpResponse("Figure asset is unavailable.", status=404, content_type="text/plain; charset=utf-8")
    response = HttpResponse(data, content_type=mime)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
