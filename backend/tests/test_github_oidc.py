import pytest

from app.github_oidc import GitHubOIDCError, validate_github_claims


VALID_CLAIMS = {
    "repository": "franarredondom/PulseOps",
    "ref": "refs/heads/main",
    "workflow_ref": (
        "franarredondom/PulseOps/.github/workflows/uptime-checks.yml@refs/heads/main"
    ),
    "event_name": "schedule",
}


def test_scheduler_claims_accept_the_expected_workflow() -> None:
    validate_github_claims(VALID_CLAIMS)


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("repository", "attacker/fork"),
        ("ref", "refs/heads/untrusted"),
        ("workflow_ref", "franarredondom/PulseOps/.github/workflows/other.yml@refs/heads/main"),
        ("event_name", "pull_request"),
    ],
)
def test_scheduler_claims_reject_untrusted_workflows(claim: str, value: str) -> None:
    claims = {**VALID_CLAIMS, claim: value}
    with pytest.raises(GitHubOIDCError):
        validate_github_claims(claims)
