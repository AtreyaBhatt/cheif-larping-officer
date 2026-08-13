"""
Delivery abstraction for sending the morning digest somewhere you'll
actually see it. Phase 1 defaults to console/log output so the pipeline
runs end-to-end with zero external accounts. TwilioWhatsAppDelivery is
included but not wired in by default — flip DELIVERY_PROVIDER env var
once you've set up a Twilio account (their WhatsApp sandbox is free for
testing: https://www.twilio.com/docs/whatsapp/sandbox).
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

from brandos.digest import ContentIdea

logger = logging.getLogger(__name__)


class DeliveryProvider(ABC):
    @abstractmethod
    def deliver(self, digest_text: str) -> None:
        raise NotImplementedError


class ConsoleDelivery(DeliveryProvider):
    """Just prints the digest. Good enough until WhatsApp is set up."""

    def deliver(self, digest_text: str) -> None:
        print("\n" + "=" * 60)
        print("MORNING DIGEST (console stub — no real delivery configured)")
        print("=" * 60)
        print(digest_text)
        print("=" * 60 + "\n")
        logger.info("Digest delivered via console stub (%d chars)", len(digest_text))


class TwilioWhatsAppDelivery(DeliveryProvider):
    """
    Sends the digest via Twilio's WhatsApp API.

    Requires env vars:
      TWILIO_ACCOUNT_SID
      TWILIO_AUTH_TOKEN
      TWILIO_WHATSAPP_FROM   (e.g. "whatsapp:+14155238886" — Twilio sandbox number)
      TWILIO_WHATSAPP_TO     (your own WhatsApp number, e.g. "whatsapp:+91XXXXXXXXXX")

    Note: Twilio's free WhatsApp *sandbox* requires re-joining every 72
    hours by sending the join code to the sandbox number from your phone.
    Fine for development; for anything long-running, either keep rejoining
    or move to a paid Twilio WhatsApp sender / Meta's Cloud API.
    """

    def __init__(self):
        # Imported lazily so `twilio` isn't a hard dependency for
        # people running the stub-only Phase 1 setup.
        from twilio.rest import Client

        account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        auth_token = os.environ["TWILIO_AUTH_TOKEN"]
        self.from_number = os.environ["TWILIO_WHATSAPP_FROM"]
        self.to_number = os.environ["TWILIO_WHATSAPP_TO"]
        self.client = Client(account_sid, auth_token)

    def deliver(self, digest_text: str) -> None:
        # WhatsApp messages via Twilio have a length cap (~1600 chars per
        # message segment); trim and point to the dashboard for the rest
        # once Phase 2 exists. For now just warn if it's long.
        if len(digest_text) > 1500:
            logger.warning(
                "Digest is %d chars, may be truncated or split by WhatsApp/Twilio",
                len(digest_text),
            )

        message = self.client.messages.create(
            from_=self.from_number,
            to=self.to_number,
            body=digest_text,
        )
        logger.info("Digest sent via Twilio WhatsApp, sid=%s", message.sid)


def get_delivery_provider() -> DeliveryProvider:
    """
    Reads DELIVERY_PROVIDER env var: "console" (default) or "twilio".
    """
    provider = os.environ.get("DELIVERY_PROVIDER", "console").lower()
    if provider == "twilio":
        return TwilioWhatsAppDelivery()
    return ConsoleDelivery()


def format_digest(ideas: list[ContentIdea]) -> str:
    """
    Turns a list of ContentIdea into the human-readable digest text,
    matching the structure from the project spec (headline / summary /
    source / angles).
    """
    if not ideas:
        return "🧠 AI Morning Digest\n\nNo ideas generated today."

    lines = ["🧠 AI Morning Digest", ""]
    for i, idea in enumerate(ideas, start=1):
        source = idea.source_articles[0] if idea.source_articles else {}
        summary = idea.digest_summary or idea.content
        lines.append(f"{i}. {idea.headline}")
        lines.append(f"   {summary}")
        if source.get("url") or source.get("hn_url"):
            lines.append(f"   Source: {source.get('url') or source.get('hn_url')}")
        if idea.category:
            lines.append(f"   Category: {idea.category}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    # Quick manual check: python -m brandos.delivery
    from brandos.digest import ContentIdea

    logging.basicConfig(level=logging.INFO)
    fake_ideas = [
        ContentIdea(
            headline="Example headline",
            content="Example summary of what happened and why it matters.",
            source_articles=[{"url": "https://example.com"}],
            category="ai",
        )
    ]
    text = format_digest(fake_ideas)
    get_delivery_provider().deliver(text)
