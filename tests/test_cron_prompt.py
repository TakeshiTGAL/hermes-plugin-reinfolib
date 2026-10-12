"""The string Hermes actually builds for the weekly job. Skips without Hermes."""
from __future__ import annotations

import pytest

import blueprint


def test_assembled_prompt_follows_the_host_silent_rule():
    prompt_mod = pytest.importorskip("cron.scheduler_prompt")
    filled = blueprint.PROMPT_TEMPLATE.format(city="13102")
    job = {"id": "jp-reinfolib-weekly", "name": "Weekly city transaction check", "prompt": filled}
    assembled = prompt_mod._build_job_prompt(job)
    assert "nothing new to report" in assembled
    assert 'exactly "[SILENT]"' in assembled
    assert "Never answer [SILENT]" not in assembled
    assert "Answer exactly [SILENT] and nothing else." in assembled
    assert "If any call has ok true, send one short message and do not use [SILENT]." in assembled
    assert filled in assembled
    assert assembled.index("nothing new to report") < assembled.index(filled)
