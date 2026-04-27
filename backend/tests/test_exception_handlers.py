from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def test_http_exception_handler_uses_message_from_detail_dict():
    from app.core.errors.exception_handlers import setup_exception_handlers

    app = FastAPI()
    setup_exception_handlers(app, debug=False)

    @app.get("/conflict")
    async def conflict():
        raise HTTPException(
            status_code=409,
            detail={
                "message": "save_in_progress",
                "active_save_request_id": "save-request-1",
            },
        )

    response = TestClient(app).get("/conflict")

    assert response.status_code == 409
    assert response.json() == {
        "code": 409,
        "message": "save_in_progress",
        "data": {
            "message": "save_in_progress",
            "active_save_request_id": "save-request-1",
        },
    }
