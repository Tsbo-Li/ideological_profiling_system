import os
import logging
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

from configs.database_cfg import DatabaseConfig
from database.db import init_engine_and_session
from database.student_repository import StudentRepository
from database.profile_repository import ProfileRepository
from services.numeric_clustering_service import NumericClusteringService
from services.text_clustering_service import TextClusteringService
from services.profile_query_service import ProfileQueryService
from services.clustering_orchestration_service import ClusteringOrchestrationService
from services.counselor_api_service import CounselorApiService
from services.ai_talking_service import AiTalkingService


def setup_logging() -> None:
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    log_dir = Path(__file__).resolve().parents[1] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers when Flask reloads in debug mode.
    if root_logger.handlers:
        root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def create_app() -> Flask:
    setup_logging()
    app = Flask(__name__)
    CORS(app)

    db_cfg = DatabaseConfig.from_env()
    engine, SessionLocal = init_engine_and_session(db_cfg.database_url)

    # Repositories (stateless wrappers around sessions)
    student_repo = StudentRepository(SessionLocal)
    profile_repo = ProfileRepository(SessionLocal)
    numeric_service = NumericClusteringService()
    text_service = TextClusteringService()
    profile_query_service = ProfileQueryService(SessionLocal)
    clustering_orchestration_service = ClusteringOrchestrationService(
        numeric_service=numeric_service,
        text_service=text_service,
    )
    ai_talking_service = AiTalkingService()
    counselor_api_service = CounselorApiService(
        session_factory=SessionLocal,
        ai_talking_service=ai_talking_service,
    )

    def success_response(data=None, message: str = "success", status_code: int = 200, meta=None):
        body = {
            "ok": True,
            "message": message,
            "data": data if data is not None else {},
        }
        if meta is not None:
            body["meta"] = meta
        return jsonify(body), status_code

    def error_response(code: str, message: str, status_code: int = 400, detail=None):
        body = {
            "ok": False,
            "message": message,
            "error": {
                "code": code,
                "detail": detail,
            },
        }
        return jsonify(body), status_code

    @app.get("/api/health")
    def health():
        return success_response(data={"service": "backend", "status": "healthy"})

    @app.get("/api/students")
    def list_students():
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        items = student_repo.list(limit=limit, offset=offset)
        return success_response(
            data=[s.to_dict() for s in items],
            meta={"limit": limit, "offset": offset},
        )

    @app.post("/api/students")
    def create_student():
        payload = request.get_json(force=True) or {}
        student = student_repo.create(payload)
        return success_response(data=student.to_dict(), status_code=201)

    @app.get("/api/students/<int:student_id>")
    def get_student(student_id: int):
        student = student_repo.get_by_id(student_id)
        if not student:
            return error_response(
                code="student_not_found",
                message="student_not_found",
                status_code=404,
                detail=f"student_id={student_id}",
            )
        return success_response(data=student.to_dict())

    @app.put("/api/students/<int:student_id>")
    def update_student(student_id: int):
        payload = request.get_json(force=True) or {}
        student = student_repo.update(student_id, payload)
        if not student:
            return error_response(
                code="student_not_found",
                message="student_not_found",
                status_code=404,
                detail=f"student_id={student_id}",
            )
        return success_response(data=student.to_dict())

    @app.delete("/api/students/<int:student_id>")
    def delete_student(student_id: int):
        ok = student_repo.delete(student_id)
        if not ok:
            return error_response(
                code="student_not_found",
                message="student_not_found",
                status_code=404,
                detail=f"student_id={student_id}",
            )
        return success_response(data={"deleted": True})

    @app.get("/api/students/<int:student_id>/profile")
    def get_profile(student_id: int):
        profile = profile_repo.get_by_student_id(student_id)
        if not profile:
            return error_response(
                code="profile_not_found",
                message="profile_not_found",
                status_code=404,
                detail=f"student_id={student_id}",
            )
        return success_response(data=profile.to_dict())

    @app.put("/api/students/<int:student_id>/profile")
    def upsert_profile(student_id: int):
        payload = request.get_json(force=True) or {}
        profile = profile_repo.upsert_for_student(student_id, payload)
        if not profile:
            return error_response(
                code="student_not_found",
                message="student_not_found",
                status_code=404,
                detail=f"student_id={student_id}",
            )
        return success_response(data=profile.to_dict())

    @app.get("/api/config")
    def config_view():
        # Only return non-sensitive config
        return success_response(
            data={
                "database_url": db_cfg.database_url_masked(),
                "env": os.getenv("APP_ENV", "dev"),
            }
        )

    @app.post("/api/clustering/run-all")
    def run_all_clustering():
        payload = request.get_json(silent=True) or {}
        result = clustering_orchestration_service.run_all(payload)
        return success_response(
            data={k: v for k, v in result.items() if k != "period"},
            meta={"period": result["period"]},
        )

    @app.get("/api/profiles")
    def list_profiles():
        period = request.args.get("period")
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        items = profile_query_service.list_profiles(period=period, limit=limit, offset=offset)
        return success_response(
            data=items,
            meta={
                "period": period,
                "limit": limit,
                "offset": offset,
            },
        )

    @app.get("/api/clustering/summary")
    def clustering_summary():
        period = request.args.get("period")
        summary = profile_query_service.clustering_summary(period=period)
        return success_response(
            data=summary,
            meta={"period": period},
        )

    @app.get("/api/profile/<string:student_id>")
    def get_profile_compat(student_id: str):
        # Frontend compatibility endpoint: return raw profile object (no envelope).
        data = counselor_api_service.get_frontend_profile(student_id)
        if data is None:
            return jsonify({"detail": "profile_or_student_not_found"}), 404
        return jsonify(data)

    @app.post("/api/counselor/students/<string:student_id>/warning-handling")
    def counselor_warning_handling(student_id: str):
        payload = request.get_json(silent=True) or {}
        status = str(payload.get("status") or "processing")
        handler = str(payload.get("handler") or "")
        note = str(payload.get("note") or "")
        data = counselor_api_service.update_warning_handling(
            student_id=student_id,
            status=status,
            handler=handler,
            note=note,
        )
        if data is None:
            return jsonify({"detail": "profile_or_student_not_found"}), 404
        return jsonify(data)

    @app.post("/api/counselor/warning-scores/recompute")
    def counselor_recompute_warning_scores():
        data = counselor_api_service.recompute_warning_scores()
        return jsonify(data)

    @app.get("/api/counselor/clusters")
    def counselor_clusters():
        method = request.args.get("method", "behavior_kmeans")
        if method == "temporal":
            method = "behavior_kmeans"
        return jsonify(counselor_api_service.get_clusters(method))

    @app.get("/api/counselor/dashboard")
    def counselor_dashboard():
        return jsonify(counselor_api_service.get_dashboard())

    @app.get("/api/counselor/groups")
    def counselor_groups():
        method = request.args.get("method", "numeric")
        return jsonify(counselor_api_service.get_groups(method=method))

    @app.get("/api/counselor/students")
    def counselor_students():
        keyword = request.args.get("keyword")
        risk_level = request.args.get("riskLevel")
        limit = int(request.args.get("limit", "20"))
        offset = int(request.args.get("offset", "0"))
        return jsonify(counselor_api_service.get_students(keyword=keyword, risk_level=risk_level, limit=limit, offset=offset))

    @app.get("/api/counselor/scatter")
    def counselor_scatter():
        method = request.args.get("method", "numeric")
        return jsonify(counselor_api_service.get_scatter_points(method=method))

    @app.get("/api/counselor/content-suggestions")
    def counselor_content_suggestions():
        return jsonify(counselor_api_service.get_content_suggestions())

    @app.get("/api/counselor/content-context")
    def counselor_content_context():
        # Privacy-safe context used for AI content generation.
        return jsonify(counselor_api_service.build_content_context())

    @app.get("/api/counselor/content-drafts/latest")
    def counselor_content_drafts_latest():
        return jsonify(counselor_api_service.get_latest_content_drafts())

    @app.get("/api/counselor/content-drafts")
    def counselor_content_drafts_list():
        kind = request.args.get("kind")
        limit = int(request.args.get("limit", "20"))
        offset = int(request.args.get("offset", "0"))
        return jsonify(counselor_api_service.list_content_drafts(kind=kind, limit=limit, offset=offset))

    @app.post("/api/counselor/content-jobs")
    def counselor_content_jobs_create():
        payload = request.get_json(silent=True) or {}
        kind = str(payload.get("kind") or "article")
        job = counselor_api_service.create_content_job(kind=kind)
        return jsonify(job), 201

    @app.get("/api/counselor/content-jobs/<int:job_id>")
    def counselor_content_jobs_get(job_id: int):
        job = counselor_api_service.get_content_job(job_id)
        if not job:
            return jsonify({"detail": "job_not_found"}), 404
        return jsonify(job)

    @app.get("/api/counselor/content-jobs/<int:job_id>/stream")
    def counselor_content_jobs_stream(job_id: int):
        from_offset = int(request.args.get("from", "0"))
        return Response(
            stream_with_context(counselor_api_service.stream_content_job(job_id=job_id, from_offset=from_offset)),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/counselor/content-generate")
    def counselor_content_generate():
        kind = (request.args.get("kind") or "article").strip().lower()
        stream = (request.args.get("stream") or "").strip().lower() in {"1", "true", "yes"}
        if not stream:
            return jsonify({"detail": "use stream=1"}), 400
        return Response(
            stream_with_context(counselor_api_service.stream_content_text(kind=kind)),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/counselor/hot-topics")
    def counselor_hot_topics():
        platform = request.args.get("platform")
        limit = int(request.args.get("limit", "10"))
        offset = int(request.args.get("offset", "0"))
        if platform:
            return jsonify(counselor_api_service.get_hot_topics_page(platform=platform, limit=limit, offset=offset))
        return jsonify(counselor_api_service.get_hot_topics(platform=platform, limit_per_platform=limit))

    @app.get("/api/counselor/talking-draft")
    def counselor_talking_draft():
        student_id = (request.args.get("studentId") or "").strip()
        if not student_id:
            return jsonify({"detail": "studentId is required"}), 400
        stream = (request.args.get("stream") or "").strip().lower() in {"1", "true", "yes"}
        if stream:
            return Response(
                stream_with_context(counselor_api_service.stream_talking_draft(student_id)),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        return jsonify(counselor_api_service.get_talking_draft(student_id))

    return app


if __name__ == "__main__":
    app = create_app()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
