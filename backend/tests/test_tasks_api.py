from fastapi.testclient import TestClient


def test_case_task_crud_flow(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Task tracking case"},
    )
    case_id = create_case.json()["id"]

    create_task = client.post(
        f"/cases/{case_id}/tasks",
        json={
            "title": "Obtain RNA validation",
            "status": "todo",
            "owner": "oncology-team",
            "due_date": "2026-04-20T12:00:00Z",
            "notes": "Need follow-up sequencing request",
        },
    )
    assert create_task.status_code == 201
    task = create_task.json()
    assert task["case_id"] == case_id
    assert task["title"] == "Obtain RNA validation"
    assert task["status"] == "todo"
    assert task["owner"] == "oncology-team"

    list_tasks = client.get(f"/cases/{case_id}/tasks")
    assert list_tasks.status_code == 200
    tasks = list_tasks.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task["id"]

    patch_task = client.patch(
        f"/tasks/{task['id']}",
        json={"status": "in_progress", "notes": "Samples sent to lab"},
    )
    assert patch_task.status_code == 200
    updated = patch_task.json()
    assert updated["status"] == "in_progress"
    assert updated["notes"] == "Samples sent to lab"


def test_missing_case_task_list_returns_404(client: TestClient) -> None:
    response = client.get("/cases/missing-case/tasks")

    assert response.status_code == 404


def test_missing_task_update_returns_404(client: TestClient) -> None:
    response = client.patch("/tasks/missing-task", json={"status": "done"})

    assert response.status_code == 404
