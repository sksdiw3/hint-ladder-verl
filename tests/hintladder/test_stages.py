from pathlib import Path
import json
import sys

import pytest
from hintladder.io import write_json, read_json, manifest
from hintladder.stages.train_hinter import run as train_hinter
from hintladder.stages.alternate import accept_candidate
from hintladder.stages.eval_behavior import audit_dump
from hintladder.scoring import three_view_scores


def test_gamefile_passthrough_handles_mixed_worker_infos():
    from agent_system.environments.env_manager import set_gamefile
    assert set_gamefile([{}, {"extra.gamefile": "b"}], ["a", "b"]) == [{"extra.gamefile":"a"},{"extra.gamefile":"b"}]
    with pytest.raises(ValueError):
        set_gamefile([{"extra.gamefile":"b"}], ["a"])
    with pytest.raises(ValueError):
        set_gamefile([{}], [None])


def test_three_view_actual_ids_and_copy_diagnostic():
    calls = []
    class Client:
        def score_tokens(self, prompt, target):
            calls.append(list(target))
            return {1:[-3,-5],2:[-1,-4],3:[-4,-2]}[prompt[0]]
    result = three_view_scores(Client(), {"clean":[1],"hinted":[2],"hint_only":[3]}, [17,19])
    assert calls == [[17,19]] * 3
    assert result["hint_ladder/lift"] == 1.5
    assert result["hint_ladder/copy"] == 1.5
    assert result["copy_is_diagnostic_only"]


def test_native_validation_dump(facts):
    rows = [{"input":"Your admissible actions of the current situation are: ['look'].", "output":"<action>look</action>", "gamefile":"a", "traj_uid":"native-id",
             "turn_step":0, "episode_rewards":10, "executed_action":"look", "is_action_valid":True}]
    assert audit_dump(rows,{"a":facts})["hint_ladder/success_rate"] == 1
    rows[0]["input"] = "<private_teacher_note>secret</private_teacher_note>"
    with pytest.raises(ValueError,match="validation"):
        audit_dump(rows,{"a":facts})


def test_acceptance_requires_both_splits():
    assert accept_candidate({"seen":.4,"unseen":.5},{"seen":.5,"unseen":.5})
    assert not accept_candidate({"seen":.4,"unseen":.5},{"seen":.9,"unseen":.4})
    with pytest.raises(ValueError):
        accept_candidate({"seen":.4},{"unseen":.4})


def fake_hf(path):
    path.mkdir()
    write_json(path / "config.json", {"test_fixture": True})
    (path / "model.safetensors").write_bytes(b"CPU interface fixture; not a real model")
    return str(path)


def test_hinter_handoff_runs_real_subprocess_and_resumes(tmp_path):
    old = fake_hf(tmp_path / "old")
    new = fake_hf(tmp_path / "new")
    source = tmp_path / "privilege.jsonl"; source.write_text("")
    config_path = tmp_path / "config.yaml"; config_path.write_text("stage: fixture\n")
    script = tmp_path / "external.py"
    script.write_text('import json,sys\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text())\nPath(r["response_path"]).write_text(json.dumps({"checkpoint":sys.argv[2],"trained_steps":1}))\n')
    config = {"stage.output_dir":str(tmp_path/'output'),"stage.hinter_checkpoint":old,"stage.student_checkpoint":old,
              "stage.privilege_banks":[str(source)],"stage.round":0,"stage.command":[sys.executable,str(script),"{request}",new]}
    train_hinter(config,config_path,0,None,[])
    script.unlink()  # Resume must use the validated response, not rerun trainer.
    train_hinter(config,config_path,0,None,[])
    assert read_json(tmp_path/'output/result.json')["checkpoint"] == new
    assert not read_json(tmp_path/'output/result.json')["reward_implemented_here"]


def test_deferred_hinter_writes_concrete_request(tmp_path):
    old = fake_hf(tmp_path / "old")
    source = tmp_path / "p.jsonl"; source.write_text("")
    config_path = tmp_path/'config.yaml'; config_path.write_text("x: 1\n")
    config = {"stage.output_dir":str(tmp_path/'output'),"stage.hinter_checkpoint":old,"stage.student_checkpoint":old,
              "stage.privilege_banks":[str(source)],"stage.round":0,"stage.command":None}
    with pytest.raises(ValueError,match="deferred"):
        train_hinter(config,config_path,0,None,[])
    assert (tmp_path/'output/training_request.json').exists()
    assert not (tmp_path/'output/result.json').exists()


def test_manifest_checksums_only_as_provenance(tmp_path):
    config = tmp_path/'config.yaml'; config.write_text('x: 1\n')
    result = manifest(tmp_path/'out','test',config,{'x':1})
    assert set(result) == {'stage','config_path','config','git_commit','inputs','created_at'}
    assert len(result['inputs'][0]['sha256']) == 64
