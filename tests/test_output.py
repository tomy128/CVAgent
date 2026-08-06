from resume_agent.output import write_artifacts


def test_outputs_isolate_application_and_aspirational_content(tmp_path) -> None:
    state = {
        "requirements": [{"id": "req-01", "category": "skill", "description": "Kubernetes"}],
        "matches": [{
            "requirement_id": "req-01", "status": "gap", "evidence_ids": [],
            "rationale": "No evidence", "missing_capability": "Kubernetes",
        }],
        "retrievals": [{"requirement_id": "req-01", "query": "Kubernetes", "hits": []}],
        "application_resume": "# Resume\n\nPython engineer",
        "target_resume": "# Target Resume — NOT FOR SUBMISSION\n\n⚠ TARGET: Kubernetes",
        "growth_plan": {"tasks": [{
            "id": "task-01", "requirement_id": "req-01", "target_capability": "Kubernetes",
            "priority": "high", "estimated_effort": "2 days", "work": "Build a lab",
            "acceptance_checks": ["Test passes"], "evidence_to_keep": ["Repository"],
            "future_resume_statement": "Built a Kubernetes lab",
        }]},
        "interview_prep": {"items": []},
    }

    write_artifacts(tmp_path, state)

    application = (tmp_path / "application-resume.md").read_text()
    assert "Kubernetes" not in application
    assert "NOT FOR SUBMISSION" in (tmp_path / "target-resume.md").read_text()
    assert "Test passes" in (tmp_path / "growth-plan.md").read_text()
