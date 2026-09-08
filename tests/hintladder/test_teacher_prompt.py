import pytest
from hintladder.teacher_prompt import ANCHOR, OPEN, insert_note, remove_note
from agent_system.environments.prompts import ALFWORLD_TEMPLATE_ACTION_TAG_ONLY, ALFWORLD_TEMPLATE_NO_HIS_ACTION_TAG_ONLY


@pytest.mark.parametrize("template", [ALFWORLD_TEMPLATE_ACTION_TAG_ONLY, ALFWORLD_TEMPLATE_NO_HIS_ACTION_TAG_ONLY])
def test_native_templates_preserve_original(template):
    text = template.format(task_description="put a mug away", current_observation="look", admissible_actions="look",
                           step_count=2, history_length=2, action_history="go to desk 1", current_step=3)
    for prompt in (text, "<|im_start|>user\n" + text + "<|im_end|>\n<|im_start|>assistant\n"):
        result = insert_note(prompt, "Observe before acting.")
        assert result.count(OPEN) == 1
        assert remove_note(result) == prompt


@pytest.mark.parametrize("text", ["no anchor", ANCHOR + "\n" + ANCHOR + "\n", ANCHOR + "\n" + OPEN])
def test_rejects_ambiguous_prompt(text):
    with pytest.raises(ValueError):
        insert_note(text, "advice")
