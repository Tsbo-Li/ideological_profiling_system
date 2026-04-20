import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from configs.database_cfg import DatabaseConfig
from database.db import init_engine_and_session
from database.student_repository import StudentRepository
from database.profile_repository import ProfileRepository


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    db_cfg = DatabaseConfig.from_env()
    engine, SessionLocal = init_engine_and_session(db_cfg.database_url)

    # Repositories (stateless wrappers around sessions)
    student_repo = StudentRepository(SessionLocal)
    profile_repo = ProfileRepository(SessionLocal)

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/api/students")
    def list_students():
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        items = student_repo.list(limit=limit, offset=offset)
        return jsonify([s.to_dict() for s in items])

    @app.post("/api/students")
    def create_student():
        payload = request.get_json(force=True) or {}
        student = student_repo.create(payload)
        return jsonify(student.to_dict()), 201

    @app.get("/api/students/<int:student_id>")
    def get_student(student_id: int):
        student = student_repo.get_by_id(student_id)
        if not student:
            return jsonify({"error": "student_not_found"}), 404
        return jsonify(student.to_dict())

    @app.put("/api/students/<int:student_id>")
    def update_student(student_id: int):
        payload = request.get_json(force=True) or {}
        student = student_repo.update(student_id, payload)
        if not student:
            return jsonify({"error": "student_not_found"}), 404
        return jsonify(student.to_dict())

    @app.delete("/api/students/<int:student_id>")
    def delete_student(student_id: int):
        ok = student_repo.delete(student_id)
        if not ok:
            return jsonify({"error": "student_not_found"}), 404
        return jsonify({"deleted": True})

    @app.get("/api/students/<int:student_id>/profile")
    def get_profile(student_id: int):
        profile = profile_repo.get_by_student_id(student_id)
        if not profile:
            return jsonify({"error": "profile_not_found"}), 404
        return jsonify(profile.to_dict())

    @app.put("/api/students/<int:student_id>/profile")
    def upsert_profile(student_id: int):
        payload = request.get_json(force=True) or {}
        profile = profile_repo.upsert_for_student(student_id, payload)
        if not profile:
            return jsonify({"error": "student_not_found"}), 404
        return jsonify(profile.to_dict())

    @app.get("/api/config")
    def config_view():
        # Only return non-sensitive config
        return jsonify(
            {
                "database_url": db_cfg.database_url_masked(),
                "env": os.getenv("APP_ENV", "dev"),
            }
        )

    return app


if __name__ == "__main__":
    app = create_app()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
