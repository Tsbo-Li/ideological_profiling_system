import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import func, select

from configs.database_cfg import DatabaseConfig
from database.db import init_engine_and_session
from database.models import Profile, Student
from database.student_repository import StudentRepository
from database.profile_repository import ProfileRepository
from services.numeric_clustering_service import NumericClusteringService
from services.text_clustering_service import TextClusteringService
from services.profile_query_service import ProfileQueryService
from services.clustering_orchestration_service import ClusteringOrchestrationService


def create_app() -> Flask:
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

    return app


if __name__ == "__main__":
    app = create_app()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
