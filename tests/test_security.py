import json

from app.security.audit import AuditTrail
from app.security.models import PolicyAction
from app.security.policy_engine import PolicyEngine


def test_policy_engine_regex(tmp_path):
    policy_file = tmp_path / "policies.yaml"
    policy_file.write_text(r"""
version: "1.0"
default_action: "allow"
rules:
  - id: "block_rm_rf"
    target_tool: "run_command"
    argument_match:
      CommandLine: '(?i).*rm\s+-r.*\s+/(?!Users|tmp|data).*'
    action: "block"
    reason: "Blocked"
  - id: "flag_sudo"
    target_tool: "run_command"
    argument_match:
      CommandLine: '(?i).*sudo\s+.*'
    action: "flag"
    reason: "Flagged"
""")

    engine = PolicyEngine(policy_file)

    # Test 1: Destructive rm -rf / outside allowed dirs
    decision1 = engine.evaluate("run_command", {"CommandLine": "rm -rf /etc/hosts"})
    assert decision1.action == PolicyAction.BLOCK

    # Test 2: Destructive rm -rf but inside allowed /tmp and /data
    decision2 = engine.evaluate("run_command", {"CommandLine": "rm -rf /tmp/test"})
    assert decision2.action == PolicyAction.ALLOW

    decision3 = engine.evaluate("run_command", {"CommandLine": "rm -rf /data/memory/snapshots"})
    assert decision3.action == PolicyAction.ALLOW

    # Test 4: Sudo usage
    decision4 = engine.evaluate("run_command", {"CommandLine": "sudo apt update"})
    assert decision4.action == PolicyAction.FLAG


def test_audit_trail_hashing(tmp_path):
    log_file = tmp_path / "audit.jsonl"
    audit = AuditTrail(log_file)

    entry1 = audit.record("test_tool", {"arg": 1}, "allow", "test reason", "success")
    assert (
        entry1.previous_hash == "0000000000000000000000000000000000000000000000000000000000000000"
    )

    entry2 = audit.record("test_tool", {"arg": 2}, "block", "denied", "failure")
    assert entry2.previous_hash == entry1.entry_hash

    # Verify file contents
    content = log_file.read_text().strip().splitlines()
    assert len(content) == 2
    data2 = json.loads(content[1])
    assert data2["previous_hash"] == entry1.entry_hash
