"""Environment settings and scenario loading."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT / "scenarios"
CALLS_DIR = ROOT / "calls"

# override=True: values in .env win over variables already set in the shell/system.
load_dotenv(ROOT / ".env", override=True)


class Settings(BaseModel):
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_ivr_test_number: str = ""
    # Ears (always Deepgram) and mouth (Deepgram Aura by default: same free credit)
    deepgram_api_key: str = ""
    tts_provider: str = "deepgram"  # deepgram | cartesia
    deepgram_voice: str = "aura-2-helena-en"
    cartesia_api_key: str = ""
    cartesia_voice_id: str = ""

    # Brain: Gemini (free tier) by default, or Claude
    llm_provider: str = "google"  # google | anthropic
    google_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"  # live call + simulator agent
    gemini_postcall_model: str = "gemini-3.6-flash"
    gemini_sim_rep_model: str = "gemini-3.6-flash"
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"  # live call: speed matters
    postcall_model: str = "claude-opus-5-5"  # after the call: accuracy matters
    sim_rep_model: str = "claude-sonnet-5"  # plays the insurance rep in the simulator

    public_url: str = ""
    port: int = 8765

    @property
    def ws_url(self) -> str:
        """Public websocket URL Twilio streams call audio to."""
        return self.public_url.replace("https://", "wss://").replace("http://", "ws://") + "/ws"

    def missing(self, *names: str) -> list[str]:
        """Names of the given settings that are empty."""
        return [n.upper() for n in names if not getattr(self, n)]

    def model_for(self, role: str) -> str:
        """role: agent | rep | postcall"""
        if self.llm_provider == "anthropic":
            return {"agent": self.llm_model, "rep": self.sim_rep_model, "postcall": self.postcall_model}[role]
        return {"agent": self.gemini_model, "rep": self.gemini_sim_rep_model,
                "postcall": self.gemini_postcall_model}[role]

    @property
    def llm_key_name(self) -> str:
        return "anthropic_api_key" if self.llm_provider == "anthropic" else "google_api_key"

    def missing_for_voice(self) -> list[str]:
        """Keys a voice session (browser or phone) needs with the chosen providers."""
        need = ["deepgram_api_key", self.llm_key_name]
        if self.tts_provider == "cartesia":
            need += ["cartesia_api_key", "cartesia_voice_id"]
        return self.missing(*need)


def load_settings() -> Settings:
    fields = Settings.model_fields
    values = {name: os.environ[name.upper()] for name in fields if os.environ.get(name.upper())}
    settings = Settings(**values)
    settings.public_url = settings.public_url.rstrip("/")
    return settings


class Practice(BaseModel):
    name: str
    city: str
    provider_name: str
    tax_id: str
    npi: str
    callback_phone: str


class Patient(BaseModel):
    name: str
    dob: str  # ISO date, YYYY-MM-DD
    member_id: str
    relationship: str = "subscriber"


class Payer(BaseModel):
    name: str
    phone: str = ""


class Scenario(BaseModel):
    practice: Practice
    patient: Patient
    payer: Payer
    objective: dict = {}


def load_scenario(name: str) -> Scenario:
    path = SCENARIOS_DIR / f"{name}.yaml"
    return Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


settings = load_settings()
