"""ALFWorld hint contracts, adapted from OPD's coevo/hints/ladder.py."""
import json
import re

from .keys import Level

PUBLIC_KEYS = {"initial_observation", "initial_admissible_commands"}
POLICY = ("Explore and observe the environment before committing to object locations. "
          "Use current admissible actions and observed contents as evidence. "
          "Meet all task conditions before placing the object.")
ALIASES = {"coffeemachine": "coffee machine", "countertop": "counter top",
           "sidetable": "side table", "sinkbasin": "sink basin", "stoveburner": "stove burner"}


def entity_aliases(entity):
    entity = str(entity).strip().lower()
    base = re.sub(r"\s+\d+$", "", entity)
    aliases = {entity, base}
    for compact, spaced in ALIASES.items():
        for text in tuple(aliases):
            aliases.add(text.replace(compact, spaced))
            aliases.add(text.replace(spaced, compact))
    return sorted(aliases, key=len, reverse=True)


def mentions(text, entity):
    return any(re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, re.I)
               for alias in entity_aliases(entity))


def audit_leak(hint, hidden_facts, tool_names=()):
    """Auditor-only diagnostic. Hidden facts never reach the L1/L2 writer."""
    findings = []
    for key in ("goal_object_location", "destination_receptacle"):
        if hidden_facts.get(key) and mentions(hint, hidden_facts[key]):
            findings.append(key)
    # Naming an exact numbered object is instance leakage; the public goal
    # already names its class (e.g. 'mug'), which alone is not an answer.
    goal = hidden_facts.get("goal_object", "")
    if goal and re.search(r"\d", goal) and re.search(r"(?<!\w)" + re.escape(goal) + r"(?!\w)", hint, re.I):
        findings.append("goal_object")
    for state, value in hidden_facts.get("goal_object_initial_states", {}).items():
        if re.search(r"\b" + re.escape(state) + r"\b", hint, re.I) and re.search(r"\b(?:is|already|initially|currently|not)\b", hint, re.I):
            findings.append(f"goal_object_initial_states.{state}")
    for name in tool_names:
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", hint):
            findings.append(f"tool:{name}")
    if re.search(r"<action>|\b[a-z]+_[a-z_]+\s*\(", hint, re.I):
        findings.append("executable_action")
    return findings


def public_input(record):
    return {key: record[key] for key in sorted(PUBLIC_KEYS)}


def generation_messages(level, payload):
    level = Level(level)
    if level in (Level.L0, Level.FULLPATH):
        raise ValueError(f"{level.value} must not call a generator")
    if level in (Level.L1, Level.L2) and set(payload) != PUBLIC_KEYS:
        raise ValueError("blind L1/L2 input must contain exactly the two public fields")
    if level == Level.L1:
        instruction = "Write a 15-40 word general household-agent policy reminder. Do not name instance facts, specific receptacles or specific objects."
    elif level == Level.L2:
        instruction = ("Write at most 100 words of blind procedural guidance using only the supplied public observation and admissible commands. "
                       "Teach a concrete sequence of unbiased evidence acquisition, inventory tracking and checking task conditions. "
                       "Do not name or enumerate ANY specific objects, receptacle classes, instance numbers, concrete actions or likely locations, "
                       "even when these names occur in the public input. Refer generically to the target, receptacles and required conditions. "
                       "Do not invent hidden locations or prioritize one unobserved receptacle as if its contents were known.")
    elif level == Level.L3:
        instruction = ("Write at most 140 words of oracle guidance. Explicitly state the supplied numbered goal object, "
                       "its location, the destination instance, and all supplied initial states. Explain a useful procedure in natural language.")
    else:
        instruction = ("Write the smallest useful private note, at most 140 words, for this agent. "
                       "Convert privileged instance facts into an evidence acquisition procedure. Do not disclose hidden answers.")
    instruction += " Output only ordinary prose. No JSON, code, bullets, function names, executable commands, or public agent reply."
    return [{"role": "system", "content": instruction},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def validate_hint(level, hint, hidden_facts=None):
    level = Level(level)
    if not isinstance(hint, str):
        raise TypeError("hint must be text")
    words = len(hint.split())
    errors = []
    if level == Level.L0:
        return [] if not hint else ["L0 must be empty"]
    if not words:
        errors.append("empty hint")
    if level == Level.FULLPATH:
        return errors
    if level == Level.L1 and not 15 <= words <= 40:
        errors.append("L1 requires 15-40 words")
    if words > (100 if level == Level.L2 else 140):
        errors.append("word cap exceeded")
    if re.search(r"```|[{}]|<action>|<private_teacher_note>|(?m:^\s*(?:[-*]|\d+\.)\s)", hint):
        errors.append("hint must be plain prose")
    if level == Level.L3:
        if hidden_facts is None:
            raise ValueError("L3 validation requires hidden facts")
        for key in ("goal_object", "goal_object_location", "destination_receptacle"):
            value = hidden_facts.get(key)
            if value and not re.search(r"(?<!\w)" + re.escape(str(value)) + r"(?!\w)", hint, re.I):
                errors.append(f"missing explicit oracle fact: {key}")
        for state in hidden_facts.get("goal_object_initial_states", {}):
            if not re.search(r"\b" + re.escape(state) + r"\b", hint, re.I):
                errors.append(f"missing initial state: {state}")
    if level == Level.HINTER:
        if hidden_facts is None:
            raise ValueError("HINTER validation requires hidden facts")
        errors.extend(audit_leak(hint, hidden_facts))
    # L1/L2 are blind: audit_leak is a separate E1 measurement, not a
    # privileged rejection-and-regeneration channel back into the writer.
    return errors


def fullpath(record):
    if record["walkthrough_verified"] is not True or not record["walkthrough_actions"]:
        raise ValueError("FULLPATH requires a verified winning walkthrough")
    return " -> ".join(record["walkthrough_actions"])
