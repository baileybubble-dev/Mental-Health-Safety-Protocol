"""Utility functions for the Mental Health Safety Protocol experiment."""

import os
import re
import json
from typing import Any, Union, Optional

from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
from langchain_openai import ChatOpenAI
from langchain_xai import ChatXAI


# -------------------------------
# Paths
# -------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROMPTS_DIR = os.path.join(_THIS_DIR, "prompts")


def format_list(value: Any) -> str:
    """Format a list into a readable string with bullet points."""
    if isinstance(value, list):
        return "\n".join([f"- {item}" for item in value])
    return str(value)


def content_to_text(content: Any) -> str:
    """
    Extract text content from various response formats.
    Handles common LangChain shapes (string, list[dict], dict).
    """
    if not content:
        return ""

    if isinstance(content, str):
        return content.strip()

    # List payload (Gemini often returns content=[{type,text,...}, ...])
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item.strip())
                continue

            if isinstance(item, dict):
                # common: {"type":"text","text":"..."}
                if "text" in item and isinstance(item["text"], str) and item["text"].strip():
                    parts.append(item["text"].strip())
                    continue

                # Gemini: {"parts":[{"text":"..."}...]}
                if "parts" in item:
                    parts_text = content_to_text(item["parts"])
                    if parts_text:
                        parts.append(parts_text)
                    continue

                # sometimes nested: {"content": ...}
                if "content" in item:
                    c_text = content_to_text(item["content"])
                    if c_text:
                        parts.append(c_text)
                    continue

        return "\n".join(parts).strip()

    # Dict payload
    if isinstance(content, dict):
        if "text" in content:
            return content_to_text(content["text"])
        if "parts" in content:
            return content_to_text(content["parts"])
        if "content" in content:
            return content_to_text(content["content"])

        string_values = [v.strip() for v in content.values() if isinstance(v, str) and v.strip()]
        return "\n".join(string_values).strip()

    return str(content).strip()


# -------------------------------
# Robust JSON extraction
# -------------------------------

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CODEFENCE_RE = re.compile(r"```(?:json)?\s*|\s*```", re.IGNORECASE)


def _strip_noise(text: str) -> str:
    text = _THINK_RE.sub("", text or "")
    text = _CODEFENCE_RE.sub("", text).strip()
    return text


def extract_first_json_object(text: str) -> Union[dict, None]:
    """
    Extract the first *balanced* JSON object from a text blob.
    Much safer than naive find('{') / rfind('}').
    """
    if not text:
        return None

    text = _strip_noise(text)

    # Find first '{' and then scan for balanced braces.
    start = text.find("{")
    if start == -1:
        return None

    in_str = False
    esc = False
    depth = 0
    end = None

    for i in range(start, len(text)):
        ch = text[i]

        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        # not in string
        if ch == '"':
            in_str = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end is None:
        return None

    candidate = text[start : end + 1].strip()

    # Try strict JSON first
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError as e:
        print(f"!!! JSON decode error: {e}")
        return None


# -------------------------------
# Prompt loading
# -------------------------------

def load_prompt(filename: str) -> str:
    """Load a prompt file from the prompts directory (relative to utils.py)."""
    path = os.path.join(_PROMPTS_DIR, filename)
    if not os.path.exists(path):
        # fallback to CWD/prompts for legacy layouts
        alt = os.path.join(os.getcwd(), "prompts", filename)
        if os.path.exists(alt):
            path = alt
        else:
            raise FileNotFoundError(f"Prompt file not found: {path} (or {alt})")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def format_probing_methodology(probing_method: dict) -> str:
    """Format probing_methodology into a readable string."""
    if not probing_method or not isinstance(probing_method, dict):
        return "N/A"

    result = []
    if "rounds_1_6_anchoring" in probing_method:
        result.append("Rounds 1-6 (Anchoring):")
        result.append(format_list(probing_method["rounds_1_6_anchoring"]))
        result.append("")

    if "rounds_7_12_encroachment" in probing_method:
        result.append("Rounds 7-12 (Encroachment):")
        result.append(format_list(probing_method["rounds_7_12_encroachment"]))
        result.append("")

    if "rounds_13_20_the_pincer" in probing_method:
        result.append("Rounds 13-20 (The Pincer):")
        result.append(format_list(probing_method["rounds_13_20_the_pincer"]))

    return "\n".join(result)


def format_demographics(demographics: dict) -> str:
    """Format demographics into a readable string."""
    if not demographics or not isinstance(demographics, dict):
        return "N/A"

    age = demographics.get("age", "N/A")
    income = demographics.get("income", "N/A")
    education = demographics.get("education_level", "N/A")

    return f"Age: {age}, Income: {income}, Education Level: {education}"


# -------------------------------
# Model builder
# -------------------------------

def build_chat_model(provider: str, role: str, temperature: float,
                     model_name_override: str = None, api_key: str = None,
                     force_json: bool = False):
    p = (provider or "openai").strip().lower()
    r = role.upper()

    gemini_safety = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }

    model_kwargs = {}
    if force_json:
        model_kwargs = {"response_format": {"type": "json_object"}}

    if p == "gemini":
        model_name = model_name_override or os.getenv(f"GEMINI_{r}_MODEL", "gemini-2.5-flash")
        gemini_kwargs = {
            "model": model_name,
            "temperature": temperature,
            "safety_settings": gemini_safety,
            "timeout": 120,
        }
        if api_key:
            gemini_kwargs["google_api_key"] = api_key
        if r == "SUT":
            gemini_kwargs["max_output_tokens"] = 8192
        return ChatGoogleGenerativeAI(**gemini_kwargs)

    elif p == "deepseek":
        model_name = model_name_override or os.getenv(f"DEEPSEEK_{r}_MODEL", "deepseek-chat")
        deepseek_api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        return ChatOpenAI(
            model=model_name,
            openai_api_key=deepseek_api_key,
            openai_api_base="https://api.deepseek.com",
            temperature=temperature,
            timeout=120,
            model_kwargs=model_kwargs
        )

    elif p == "xai":
        model_name = model_name_override or os.getenv(f"XAI_{r}_MODEL", "grok-3")
        xai_api_key = api_key or os.getenv("XAI_API_KEY")
        return ChatXAI(
            model=model_name,
            api_key=xai_api_key,
            temperature=temperature,
            timeout=120,
            model_kwargs=model_kwargs
        )

    else:
        model_name = model_name_override or os.getenv(f"OPENAI_{r}_MODEL", "gpt-5.2")
        openai_api_key = api_key or os.getenv("OPENAI_API_KEY_OVERRIDE") or os.getenv("OPENAI_API_KEY")
        return ChatOpenAI(
            model=model_name,
            api_key=openai_api_key,
            temperature=temperature,
            timeout=120,
            model_kwargs=model_kwargs
        )