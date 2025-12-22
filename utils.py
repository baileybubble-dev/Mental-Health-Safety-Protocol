"""Utility functions for the Mental Health Safety Protocol experiment."""

import os
import re
import json
from typing import Any, Union

from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
from langchain_openai import ChatOpenAI
from langchain_xai import ChatXAI


def format_list(value: Any) -> str:
    """Format a list into a readable string with bullet points."""
    if isinstance(value, list):
        return "\n".join([f"- {item}" for item in value])
    return str(value)


def content_to_text(content: Any) -> str:
    """Extract text content from various response formats, with special handling for Gemini."""
    if not content: 
        return ""
    
    # Handle string directly
    if isinstance(content, str): 
        return content.strip() if content.strip() else ""
    
    # Handle list (common in LangChain responses, especially Gemini)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str): 
                parts.append(item)
            elif isinstance(item, dict):
                # Handle Gemini's potential nested structure
                if "text" in item:
                    text_val = item["text"]
                    if isinstance(text_val, str):
                        parts.append(text_val)
                    elif isinstance(text_val, list):
                        # Recursively handle nested lists
                        parts.append(content_to_text(text_val))
                elif "parts" in item:  # Gemini-specific structure
                    for part in item["parts"]:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict):
                            if "text" in part:
                                parts.append(str(part["text"]))
                            # Handle other Gemini part types
                            elif "function_call" in part or "function_response" in part:
                                # Skip function calls for now
                                pass
        result = "\n".join(parts)
        return result.strip() if result.strip() else ""
    
    # Handle dict (Gemini might return dict with nested content)
    if isinstance(content, dict):
        # Try common keys
        if "text" in content:
            text_val = content["text"]
            if isinstance(text_val, str):
                return text_val.strip()
            return content_to_text(text_val)
        if "parts" in content:
            return content_to_text(content["parts"])
        if "content" in content:
            return content_to_text(content["content"])
        # Try to extract any string values
        string_values = [str(v) for v in content.values() if isinstance(v, str) and v.strip()]
        if string_values:
            return "\n".join(string_values)
    
    # Fallback: convert to string
    result = str(content)
    return result.strip() if result and result != "None" and result.strip() else ""


def extract_first_json_object(text: str) -> Union[dict, None]:
    """Extract the first JSON object from text, handling markdown code blocks and other formatting."""
    if not text: 
        return None
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'`<think>`.*?`</think>`', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'```json\s*|\s*```', '', text).strip()  # Only remove markdown code block markers, not all whitespace
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1: 
        return None
    candidate = text[start : end + 1]
    try:
        candidate = candidate.replace('\n', ' ').replace('\r', '')
        result = json.loads(candidate)
        # Ensure we return a dict, not a string or other type
        if isinstance(result, dict):
            return result
        return None
    except json.JSONDecodeError as e:
        print(f"!!! JSON decode error: {e}")
        try:
            import ast
            result = ast.literal_eval(candidate)
            if isinstance(result, dict):
                return result
            return None
        except Exception:
            return None


def load_prompt(filename: str) -> str:
    """Load a prompt file from the prompts directory."""
    path = os.path.join("prompts", filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file {path} not found!")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def format_probing_methodology(probing_method: dict) -> str:
    """Format probing_methodology into a readable string."""
    if not probing_method or not isinstance(probing_method, dict):
        return "N/A"
    
    result = []
    if 'rounds_1_6_anchoring' in probing_method:
        result.append("Rounds 1-6 (Anchoring):")
        result.append(format_list(probing_method['rounds_1_6_anchoring']))
        result.append("")
    
    if 'rounds_7_12_encroachment' in probing_method:
        result.append("Rounds 7-12 (Encroachment):")
        result.append(format_list(probing_method['rounds_7_12_encroachment']))
        result.append("")
    
    if 'rounds_13_20_the_pincer' in probing_method:
        result.append("Rounds 13-20 (The Pincer):")
        result.append(format_list(probing_method['rounds_13_20_the_pincer']))
    
    return "\n".join(result)


def format_demographics(demographics: dict) -> str:
    """Format demographics into a readable string."""
    if not demographics or not isinstance(demographics, dict):
        return "N/A"
    
    age = demographics.get('age', 'N/A')
    income = demographics.get('income', 'N/A')
    education = demographics.get('education_level', 'N/A')
    
    return f"Age: {age}, Income: {income}, Education Level: {education}"


def build_chat_model(provider: str, role: str, temperature: float, model_name_override: str = None):
    """Build a chat model based on provider, role, and temperature settings.
    
    Args:
        provider: Model provider (openai, gemini, deepseek, xai)
        role: Role (AS or SUT)
        temperature: Temperature setting
        model_name_override: Optional model name to override environment variable/default
    """
    p = (provider or "openai").strip().lower()
    r = role.upper()
    
    gemini_safety = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    
    model_kwargs = {}
    if r == "AS":
        model_kwargs = {"response_format": {"type": "json_object"}}

    if p == "gemini":
        model_name = model_name_override or os.getenv(f"GEMINI_{r}_MODEL", "gemini-2.5-flash")
        gemini_kwargs = {
            "model": model_name,
            "temperature": temperature,
            "safety_settings": gemini_safety,
            "timeout": 120,  # Set timeout to 120 seconds
        }
        # Add max_output_tokens to ensure responses aren't truncated
        # Default is usually 8192, but we can set it explicitly
        if r == "SUT":
            # For SUT, we want longer responses
            gemini_kwargs["max_output_tokens"] = 8192
        
        return ChatGoogleGenerativeAI(**gemini_kwargs)
    elif p == "deepseek":
        model_name = model_name_override or os.getenv(f"DEEPSEEK_{r}_MODEL", "deepseek-chat")
        return ChatOpenAI(
            model=model_name,
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=temperature,
            timeout=120,  # Set timeout to 120 seconds
            model_kwargs=model_kwargs
        )
    elif p == "xai":
        model_name = model_name_override or os.getenv(f"XAI_{r}_MODEL", "grok-3")
        xai_api_key = os.getenv("XAI_API_KEY")
        return ChatXAI(
            model=model_name,
            api_key=xai_api_key,
            temperature=temperature,
            timeout=120,  # Set timeout to 120 seconds
            model_kwargs=model_kwargs
        )
    else:
        model_name = model_name_override or os.getenv(f"OPENAI_{r}_MODEL", "gpt-5.2")
        # 支持通过环境变量覆盖API key（用于多terminal运行不同API key）
        api_key = os.getenv("OPENAI_API_KEY_OVERRIDE") or os.getenv("OPENAI_API_KEY")
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
            timeout=120,  # Set timeout to 120 seconds
            model_kwargs=model_kwargs
        )

