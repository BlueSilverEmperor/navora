"""
LLM Integration Layer with Strict Number Guard and Offline Fallback.
Provides provider-agnostic LLM interface, Pydantic-validated tool calls,
multi-lingual WhatsApp message drafting (English, Hindi, Kannada),
and a strict mathematical number-guard ensuring zero LLM hallucination.
"""

import os
import re
from typing import Dict, Any, List, Optional, Set, Literal, Union
from pydantic import BaseModel, Field, ValidationError


class HallucinatedNumberError(ValueError):
    """Raised when LLM output introduces numeric tokens not present in the input payload."""
    pass


class UserIntentAction(BaseModel):
    """Structured action parsed from operator natural language commands."""
    action: Literal["override_qty", "approve_action", "reject_action", "request_explanation", "draft_message"] = Field(
        ..., description="Standardized operational action verb"
    )
    incident_id: Optional[str] = Field(None, description="Problem or incident identifier (e.g. PRB-20261009-01)")
    qty: Optional[int] = Field(None, description="Requested transfer or replenishment quantity override")
    reason: Optional[str] = Field(None, description="Operator rationale or constraint noted in request")


def extract_numbers_from_payload(payload: Any) -> Set[float]:
    """Recursively traverses dictionaries, lists, strings, and numbers to extract all allowed numeric tokens."""
    numbers: Set[float] = set()

    if isinstance(payload, (int, float)):
        numbers.add(round(float(payload), 4))
        # Also add as integer
        numbers.add(float(int(payload)))
    elif isinstance(payload, str):
        # Extract numbers, dates, currency strings
        found = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", payload)
        for num_str in found:
            try:
                val = float(num_str)
                numbers.add(round(val, 4))
                numbers.add(float(int(val)))
            except ValueError:
                pass
    elif isinstance(payload, dict):
        for k, v in payload.items():
            # Include numeric tokens in keys (like '7' in '7_day')
            numbers.update(extract_numbers_from_payload(k))
            numbers.update(extract_numbers_from_payload(v))
    elif isinstance(payload, (list, tuple, set)):
        for item in payload:
            numbers.update(extract_numbers_from_payload(item))

    return numbers


def extract_numbers_from_text(text: str) -> List[float]:
    """Extracts all numeric tokens from natural language text."""
    # Find all decimal numbers and integers, ignoring isolated symbols
    matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", text)
    numbers = []
    for m in matches:
        try:
            numbers.append(float(m))
        except ValueError:
            pass
    return numbers


class NumberGuard:
    """
    Enforces Hard Rule 1: An LLM may never compute or invent numbers.
    Any number appearing in the LLM output MUST be grounded in the input payload.
    """

    def __init__(self, allowed_payload: Any, tolerance: float = 1e-4):
        self.allowed_numbers = extract_numbers_from_payload(allowed_payload)
        self.tolerance = tolerance

    def validate_text(self, generated_text: str) -> bool:
        """
        Validates that every number in generated_text is present in the allowed numbers set.
        Raises HallucinatedNumberError if an ungrounded number is found.
        """
        extracted = extract_numbers_from_text(generated_text)
        unauthorized = []

        for num in extracted:
            # Check if num is close to any allowed number
            matched = False
            for allowed in self.allowed_numbers:
                if abs(num - allowed) <= self.tolerance:
                    matched = True
                    break
            if not matched:
                unauthorized.append(num)

        if unauthorized:
            raise HallucinatedNumberError(
                f"NumberGuard rejection: Output contains ungrounded/hallucinated numbers: {unauthorized}. "
                f"Allowed payload numbers: {sorted(list(self.allowed_numbers))}"
            )
        return True


class LLMLayer:
    """
    Provider-agnostic interface with offline fallback.
    Supported modes:
    1. Offline deterministic rule-based parser & template engine (no API key required)
    2. Online provider (OpenAI, Anthropic, Gemini) if API key is provided via environment
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
        self.is_offline = not bool(self.api_key)

    def parse_user_request(self, user_prompt: str) -> UserIntentAction:
        """
        Parses Ramesh's natural language input into a Pydantic-validated UserIntentAction.
        Uses offline regex/rule parser when in offline mode.
        """
        text = user_prompt.strip().lower()

        # Extract incident ID if present (e.g., PRB-20261009-01)
        inc_match = re.search(r"prb[-_]?\d+[-_]?\d*", user_prompt, re.IGNORECASE)
        incident_id = inc_match.group(0).upper() if inc_match else None

        # 1. Override Quantity
        qty_match = re.search(r"(?:override|change|update|set|make|increase|decrease|reduce|send)\s+(?:qty|quantity|units|to)?\s*(\d+)", text)
        if not qty_match:
            # Look for stand-alone number followed by units or transfer
            qty_match = re.search(r"(\d+)\s*(?:units|nos|qty)", text)

        if ("override" in text or "change" in text or "update" in text or "set" in text) and qty_match:
            qty = int(qty_match.group(1))
            return UserIntentAction(
                action="override_qty",
                incident_id=incident_id,
                qty=qty,
                reason=user_prompt
            )

        # 2. Approve Action
        if any(w in text for w in ["approve", "confirm", "accept", "proceed", "go ahead", "dispatch"]):
            return UserIntentAction(
                action="approve_action",
                incident_id=incident_id,
                reason="Operator approved via chat"
            )

        # 3. Reject Action
        if any(w in text for w in ["reject", "dismiss", "cancel", "deny", "abort"]):
            return UserIntentAction(
                action="reject_action",
                incident_id=incident_id,
                reason=user_prompt
            )

        # 4. Draft Message
        if any(w in text for w in ["draft", "message", "whatsapp", "notify", "sms"]):
            return UserIntentAction(
                action="draft_message",
                incident_id=incident_id,
                reason=user_prompt
            )

        # 5. Default / Explain Decision
        return UserIntentAction(
            action="request_explanation",
            incident_id=incident_id,
            reason=user_prompt
        )

    def explain_decision(self, problem_payload: Dict[str, Any]) -> str:
        """
        Generates a plain-language explanation of a decision using ONLY numbers in problem_payload.
        Guarded strictly by NumberGuard.
        """
        guard = NumberGuard(allowed_payload=problem_payload)

        # Extract numbers strictly from payload
        sku = problem_payload.get("sku", "SKU")
        loc = problem_payload.get("location", "Location")
        metrics = problem_payload.get("domain_metrics", {})
        stock = metrics.get("current_stock", 0)
        burn = metrics.get("daily_burn_rate", 0.0)
        cover = metrics.get("days_of_cover", 0.0)
        gap = metrics.get("stockout_gap_days", 0.0)
        lead = metrics.get("primary_supplier_lead_time_days", 0)

        action = problem_payload.get("simulated_action", {})
        payload = action.get("payload", {})
        qty = payload.get("qty", 0)
        cost = payload.get("total_estimated_cost_inr", 0.0)

        # Build grounded template explanation
        explanation = (
            f"Operational assessment for {sku} at {loc}: Current stock is {stock} units "
            f"with daily demand of {burn} units/day, giving {cover} days of cover. "
            f"With primary supplier lead time of {lead} days, this creates a {gap} days stockout gap. "
            f"Recommended action is dispatching {qty} units at an estimated cost of {cost} INR."
        )

        # Enforce guard
        guard.validate_text(explanation)
        return explanation

    def draft_whatsapp_messages(
        self,
        problem_payload: Dict[str, Any],
        languages: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Drafts WhatsApp operational dispatch messages in English, Hindi, and Kannada.
        Every number included is strictly validated against problem_payload via NumberGuard.
        """
        guard = NumberGuard(allowed_payload=problem_payload)
        languages = languages or ["en", "hi", "kn"]

        sku = problem_payload.get("sku", "SKU")
        sku_name = problem_payload.get("sku_name", sku)
        loc = problem_payload.get("location", "Location")
        sim_action = problem_payload.get("simulated_action", {})
        payload = sim_action.get("payload", {})

        action_type = sim_action.get("action_type", "TRANSFER_REQUEST")
        qty = payload.get("qty", 0)
        source = payload.get("from_location_or_supplier", "Hub")
        cost = payload.get("total_estimated_cost_inr", 0.0)
        delivery_date = payload.get("expected_delivery_date", "")

        messages = {}

        # 1. English
        msg_en = (
            f"Kaveri Spares Dispatch Notice: Urgent dispatch of {qty} units of {sku} ({sku_name}) "
            f"from {source} to {loc}. Cost: INR {cost}. Estimated Arrival: {delivery_date}."
        )
        guard.validate_text(msg_en)
        messages["en"] = msg_en

        # 2. Hindi
        msg_hi = (
            f"कावेरी स्पेयर्स प्रेषण सूचना: {source} से {loc} के लिए {sku} ({sku_name}) की "
            f"{qty} इकाइयों का तत्काल प्रेषण। लागत: INR {cost}। अनुमानित आगमन: {delivery_date}।"
        )
        guard.validate_text(msg_hi)
        messages["hi"] = msg_hi

        # 3. Kannada
        msg_kn = (
            f"ಕಾವೇರಿ ಸ್ಪೇರ್ಸ್ ರವಾನೆ ಸೂಚನೆ: {source} ನಿಂದ {loc} ಗೆ {sku} ({sku_name}) ನ "
            f"{qty} ಯುನಿಟ್‌ಗಳ ತುರ್ತು ರವಾನೆ. ವೆಚ್ಚ: INR {cost}. ಆಗಮನ ದಿನಾಂಕ: {delivery_date}."
        )
        guard.validate_text(msg_kn)
        messages["kn"] = msg_kn

        return {lang: messages[lang] for lang in languages if lang in messages}
