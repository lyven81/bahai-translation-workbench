import json
import os
import re

import anthropic

# ---------------------------------------------------------------------------
# Multi-LLM Adapter — Demo mode: Claude only
# Users bring their own Anthropic API key via the frontend (X-API-Key header).
# Other providers are defined for future use but disabled in the public demo.
# ---------------------------------------------------------------------------

AVAILABLE_MODELS = {
    "claude": {"label": "Claude (Anthropic)", "model_id": "claude-sonnet-4-6", "provider": "anthropic"},
    "gpt4": {"label": "GPT-4 (OpenAI)", "model_id": "gpt-4o", "provider": "openai"},
    "gemini": {"label": "Gemini (Google)", "model_id": "gemini-2.0-flash", "provider": "google"},
    "deepseek": {"label": "DeepSeek", "model_id": "deepseek-chat", "provider": "deepseek"},
}

DEFAULT_MODEL = "claude"

# In demo mode, only the Anthropic provider is enabled. Other providers are
# listed in the UI but disabled so users understand what the full app supports.
DEMO_MODE_ENABLED_PROVIDERS = {"anthropic"}


def get_available_models():
    """Return models with availability info.
    In demo mode: Claude is always "available" (user brings their own key).
    Other providers are "disabled" with a reason shown in the UI.
    """
    result = []
    for key, info in AVAILABLE_MODELS.items():
        provider = info["provider"]
        enabled = provider in DEMO_MODE_ENABLED_PROVIDERS
        entry = {
            "id": key,
            "label": info["label"],
            "provider": provider,
            "available": enabled,
        }
        if not enabled:
            entry["reason"] = "Disabled in public demo. Available in self-hosted version."
        result.append(entry)
    return result


def _call_llm(system_prompt, user_message, model_key=None, temperature=0.3, max_tokens=4096, api_key=None):
    """Unified LLM call that routes to the correct provider.
    In demo mode, only the Anthropic provider is active. The caller's api_key
    is required and passed directly to Anthropic (never stored on the server).
    """
    model_key = model_key or DEFAULT_MODEL
    model_info = AVAILABLE_MODELS.get(model_key, AVAILABLE_MODELS[DEFAULT_MODEL])
    provider = model_info["provider"]
    model_id = model_info["model_id"]

    if provider not in DEMO_MODE_ENABLED_PROVIDERS:
        raise ValueError(
            f"Demo mode supports Claude (Anthropic) only. "
            f"The selected model ({model_info['label']}) is disabled in this deployment. "
            f"Please set all pipeline stages to Claude in Pipeline Settings."
        )

    if provider == "anthropic":
        if not api_key:
            raise ValueError("Anthropic API key is required. Please enter your key in the app.")
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model_id, max_tokens=max_tokens, temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text, model_id

    raise ValueError(f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_glossary(path="glossary.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_glossary_for_prompt(glossary):
    lines = []
    for term in glossary:
        line = f'- "{term["english"]}" \u2192 "{term["chinese"]}"'
        if term.get("notes"):
            line += f"  ({term['notes']})"
        lines.append(line)
    return "\n".join(lines)


def _strip_markdown_fences(text):
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip())
    return cleaned


def _unwrap_text(raw, target_keys=None):
    """Recursively unwrap JSON/markdown until plain text is found."""
    if target_keys is None:
        target_keys = ["translation", "edited_text", "typeset_text"]
    text = raw
    for _ in range(5):
        text = _strip_markdown_fences(text)
        if text.strip().startswith("{"):
            try:
                data = json.loads(text)
                extracted = None
                for k in target_keys:
                    if k in data and isinstance(data[k], str):
                        extracted = data[k]
                        break
                if extracted:
                    text = extracted
                    continue
                else:
                    break
            except (json.JSONDecodeError, TypeError):
                break
        else:
            break
    return text


def _parse_json_response(text):
    cleaned = _strip_markdown_fences(text)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            for key in list(parsed.keys()):
                if isinstance(parsed[key], str) and (parsed[key].strip().startswith("```") or parsed[key].strip().startswith("{")):
                    parsed[key] = _unwrap_text(parsed[key])
            return parsed
        except json.JSONDecodeError:
            pass
    return None


# ---------------------------------------------------------------------------
# Stage 1: Translation Agent
# ---------------------------------------------------------------------------

TRANSLATION_SYSTEM_PROMPT = """You are translating Baha'i Sacred Writings into Chinese (简体中文).

Three standards govern your translation:
1. ACCURACY (准确): Faithful to the original meaning. Never add, omit, or reinterpret.
2. BEAUTY (文风优美): Elevated, literary Chinese register. Not colloquial. The language must carry the weight and dignity of sacred scripture. Follow the poetic, classical-influenced modern Chinese style — not contemporary casual language.
3. CONSISTENCY (风格一致): Consistent with the translation style established by Shoghi Effendi (the Guardian). Use formal, classical-influenced modern Chinese. Use Chinese punctuation marks (，。；：！？""''《》).

TERMINOLOGY GLOSSARY — You MUST use these approved translations for the following terms:
{glossary_block}

RULES:
- Translate the complete text. Do not summarize or skip any passage.
- Preserve paragraph structure from the source.
- For terms in the glossary, use the approved Chinese translation exactly.
- For proper nouns not in the glossary, transliterate and add the original in parentheses on first occurrence.
- Do not add explanatory notes or commentary within the translation itself.

Return your output as JSON with these keys:
- "translation": the complete Chinese translation (string)
- "term_usage": list of glossary terms you applied, each as {{"english": "...", "chinese": "..."}}
- "notes": any translator notes on difficult passages or choices made (string)

Return ONLY the JSON object, no other text."""


def translation_agent(source_text, source_lang, glossary, model_key=None, api_key=None):
    glossary_block = format_glossary_for_prompt(glossary)
    system_prompt = TRANSLATION_SYSTEM_PROMPT.replace("{glossary_block}", glossary_block)
    lang_label = {"en": "English", "ar": "Arabic", "fa": "Persian"}.get(source_lang, "English")
    user_message = f"Translate the following {lang_label} text into Chinese:\n\n{source_text}"

    response_text, model_used = _call_llm(system_prompt, user_message, model_key=model_key, temperature=0.3, api_key=api_key)
    prompt_record = f"[System]\n{system_prompt}\n\n[User]\n{user_message}"

    parsed = _parse_json_response(response_text)
    if parsed and "translation" in parsed:
        result = {"translation": parsed["translation"], "term_usage": parsed.get("term_usage", []), "notes": parsed.get("notes", "")}
    else:
        result = {"translation": response_text, "term_usage": [], "notes": "Warning: Could not parse structured response. Raw output used."}

    result["prompt_used"] = prompt_record
    result["model_used"] = model_used
    return result


# ---------------------------------------------------------------------------
# Stage 3: Editing Agent
# ---------------------------------------------------------------------------

EDITING_SYSTEM_PROMPT = """You are a Chinese language editor for Baha'i Sacred Writings translation.

You will receive:
1. The original source text
2. A human-approved Chinese translation (from Stage 2 review)

Your task: Refine the translation for grammar, punctuation, tone, and terminology uniformity. Do NOT change the meaning — the human reviewer has already approved the meaning.

Three-standard checklist — evaluate and improve against each:
1. ACCURACY (准确): Does the translation faithfully convey the original? Flag any drift you notice but do not alter meaning.
2. BEAUTY (文风优美): Is the Chinese elevated and literary? Fix colloquial phrasing. Improve rhythm and flow. Ensure the language carries the weight of sacred scripture.
3. CONSISTENCY (风格一致): Are terms used uniformly throughout? Check against the glossary below. Ensure Chinese punctuation is used consistently.

TERMINOLOGY GLOSSARY:
{glossary_block}

RULES:
- Make minimal necessary changes. Respect the human reviewer's approved meaning.
- Fix punctuation: use Chinese punctuation marks (，。；：！？""''《》).
- Ensure paragraph structure matches the source.
- Do not add or remove content.
- For each change you make, provide a brief rationale.

Return your output as JSON with these keys:
- "edited_text": the refined Chinese translation (string)
- "changes_made": list of changes, each as a string describing what was changed and why
- "checklist": object with keys "accuracy", "beauty", "consistency", each containing a brief assessment note (string)

Return ONLY the JSON object, no other text."""


def editing_agent(source_text, approved_translation, glossary, model_key=None, api_key=None):
    glossary_block = format_glossary_for_prompt(glossary)
    system_prompt = EDITING_SYSTEM_PROMPT.replace("{glossary_block}", glossary_block)
    user_message = f"ORIGINAL SOURCE TEXT:\n{source_text}\n\nHUMAN-APPROVED CHINESE TRANSLATION:\n{approved_translation}"

    response_text, model_used = _call_llm(system_prompt, user_message, model_key=model_key, temperature=0.2, api_key=api_key)
    prompt_record = f"[System]\n{system_prompt}\n\n[User]\n{user_message}"

    parsed = _parse_json_response(response_text)
    if parsed and "edited_text" in parsed:
        result = {"edited_text": parsed["edited_text"], "changes_made": parsed.get("changes_made", []), "checklist": parsed.get("checklist", {"accuracy": "", "beauty": "", "consistency": ""})}
    else:
        result = {"edited_text": response_text, "changes_made": ["Warning: Could not parse structured response."], "checklist": {"accuracy": "N/A", "beauty": "N/A", "consistency": "N/A"}}

    result["prompt_used"] = prompt_record
    result["model_used"] = model_used
    return result


# ---------------------------------------------------------------------------
# Stage 4: Typesetting Agent
# ---------------------------------------------------------------------------

TYPESETTING_SYSTEM_PROMPT = """You are a Chinese typesetting validator for Baha'i Sacred Writings translation.

You will receive:
1. The original source text
2. An edited Chinese translation (from Stage 3 editing)

Your task: Validate and fix FORMATTING ONLY. Do NOT change wording, meaning, or style. The meaning and style have already been approved by a human reviewer and refined by an editor.

Check and fix these formatting issues:
1. PUNCTUATION CONSISTENCY: All punctuation must be Chinese marks (，。；：！？""''《》). Replace any remaining English punctuation (,.;:!?"'<>) with Chinese equivalents.
2. PARAGRAPH ALIGNMENT: The number of paragraphs in the translation must match the source text exactly.
3. SCRIPTURE REFERENCES: Book and scripture titles must use Chinese book title markers 《》 (e.g., 《亚格达斯经》, 《隐言经》).
4. QUOTATION MARKS: Use Chinese quotation marks ""'' consistently. No mixing with English quotes.
5. SPACING: Remove unnecessary spaces between Chinese characters. Keep spaces only around parenthesized original terms.

RULES:
- Make ONLY formatting changes. Never alter wording or meaning.
- If no formatting issues are found, return the text unchanged.
- For each issue found, describe what was fixed.

Return your output as JSON with these keys:
- "typeset_text": the formatting-corrected Chinese text (string)
- "issues_found": list of formatting issues detected and fixed (list of strings)
- "validation_checklist": object with keys "punctuation_consistency", "paragraph_alignment", "scripture_references", "quotation_marks", each as "pass" or "fixed" with a brief note

Return ONLY the JSON object, no other text."""


def typesetting_agent(source_text, edited_text, glossary, model_key=None, api_key=None):
    system_prompt = TYPESETTING_SYSTEM_PROMPT
    user_message = f"ORIGINAL SOURCE TEXT:\n{source_text}\n\nEDITED CHINESE TRANSLATION (from Stage 3):\n{edited_text}"

    response_text, model_used = _call_llm(system_prompt, user_message, model_key=model_key, temperature=0.1, api_key=api_key)
    prompt_record = f"[System]\n{system_prompt}\n\n[User]\n{user_message}"

    parsed = _parse_json_response(response_text)
    if parsed and "typeset_text" in parsed:
        result = {"typeset_text": parsed["typeset_text"], "issues_found": parsed.get("issues_found", []), "validation_checklist": parsed.get("validation_checklist", {})}
    else:
        result = {"typeset_text": response_text, "issues_found": ["Warning: Could not parse structured response."], "validation_checklist": {}}

    result["prompt_used"] = prompt_record
    result["model_used"] = model_used
    return result
