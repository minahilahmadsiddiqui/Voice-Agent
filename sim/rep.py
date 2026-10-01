"""The simulated insurance rep: a scripted phone menu + hold, then an LLM playing the rep."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

PERSONAS_DIR = Path(__file__).parent / "personas"

PAUSE = "<pause>"
HANGUP = "<hangup>"


@dataclass
class IvrStep:
    say: str
    expect_digits: str | None = None  # keys the agent must press
    expect_speech: str | None = None  # word the agent must say (case-insensitive)


@dataclass
class Persona:
    name: str
    description: str
    rep_name: str
    facts: str
    behavior: str
    today: str
    ivr: list[IvrStep] = field(default_factory=list)
    hold_messages: list[str] = field(default_factory=list)
    ground_truth: str = ""  # file in sim/ground_truth


def load_persona(name: str) -> Persona:
    data = yaml.safe_load((PERSONAS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    data["ivr"] = [IvrStep(**s) for s in data.get("ivr", [])]
    return Persona(**data)


def rep_system_prompt(p: Persona) -> str:
    return f"""You are role-playing {p.rep_name}, a provider-services representative at a dental insurance company, on a live phone call. The caller is an automated assistant calling on behalf of a dental practice to verify benefits. This is a test of that assistant: play your part realistically.

# The member's plan (your screen). Only give what is asked; never volunteer extra facts.
{p.facts}

# How you behave
{p.behavior}

# Output format
- Output only the words you say aloud on the phone. No stage directions, no narration.
- Keep turns short and natural, like a busy rep (usually one or two sentences).
- When you would say something like "let me pull that up" and then keep talking after looking, write {PAUSE} between the two parts, e.g. "Let me look.{PAUSE}I show two claims..."
- When the call is over (the caller said goodbye), say a short goodbye and then write {HANGUP}.
"""


class RepSim:
    def __init__(self, persona: Persona, client):
        self.persona = persona
        self.client = client
        # From the rep's side, the agent is the "user".
        self.messages: list[dict] = [
            {"role": "user", "content": "[The call has been connected to you from the hold queue. Greet the caller.]"}
        ]

    async def say(self) -> str:
        reply = await self.client.create(
            system=rep_system_prompt(self.persona), messages=self.messages, max_tokens=300, temperature=0.7,
        )
        text = reply.text
        self.messages.append({"role": "assistant", "content": text or "..."})
        return text

    async def reply(self, agent_said: str) -> str:
        self.messages.append({"role": "user", "content": agent_said or "[silence]"})
        return await self.say()
