"""
Submit the five WhatsApp notification templates to Meta (via the Gupshup Partner API).

These back app/services/gupshup/notifications.py — the WhatsApp mirror of Aura's in-app
notifications. Meta only assigns a template id once it approves the template, so the flow is:

    1. run this script          -> templates submitted, ids printed
    2. paste the printed ids into .env / the deploy secrets
    3. wait for Meta's approval (minutes to a few hours; check
       GET /api/system/whatsapp/templates or the Gupshup dashboard)

All five are submitted as UTILITY with allow_template_category_change=False, deliberately.
A UTILITY template reaches every verified number at utility pricing with no marketing
opt-in — which is the whole point here. Meta may still disagree about the two broadcast
templates (aura_new_masterclass / aura_resource_added) and read a "new content is live"
message as promotional; with category change disallowed that comes back as a visible
rejection rather than a silent reclassification to MARKETING pricing and opt-in-only reach.
If one is rejected, either soften the copy toward "your subscription now includes..." or
resubmit that single template as MARKETING with eyes open.

Copy rules worth keeping if you edit the bodies: no params in the header/footer, no newline
or tab inside a {{n}} value (the sender collapses whitespace for this reason), and every body
opens with the user's name as {{1}} — the sender always passes name first.

Three of the buttons deep-link to the exact session/resource the message is about, via a
variable at the tail of the button URL (Meta only allows one, and only at the very end).
A button variable is numbered independently of the body — both start at {{1}} — but at send
time they share one flat params list, body variables first and button variables last. So
aura_resource_added, with two body variables and one button variable, is sent as
[name, category_label, resource_name, resource_id]. Change a body variable count here and
the button param has to move with it in notifications.py.

Changing the copy of a template that's already been submitted means resubmitting it — Meta
reviewed what you sent, and it only lets you edit a template that has come back APPROVED or
REJECTED, not one still PENDING. While it's pending the practical move is to delete it and
submit again, which --replace does in one step. Note that a resubmitted template gets a NEW
id, so re-copy the printed WA_TEMPLATE_* value even if you'd already saved the old one.

Deletion is asynchronous on Meta's side, and until it finishes, resubmitting the same
name+language fails with "New English (US) content can't be added while the existing English
(US) content is being deleted". Hence DELETE_SETTLE_SECONDS below. How long that takes is
Meta's call and it varies wildly — usually under a minute, but it can come back as a 4-week
lock on that one name+language pair, which no amount of waiting shortens. When that happens
the way out is to resubmit under a different language (--language) or a different
element_name; the ids the sender uses are per-template, so neither changes anything at
send time.

That lock is why three of these are named the way they are. They were first submitted as
aura_guided_viz_ready / aura_eft_ready / aura_new_resource, deleted to correct their button
URLs, and those names are now unusable in either English until the lock clears — hence
aura_visualisation_ready / aura_tapping_ready / aura_resource_added. Nothing but this file
names them, so the rename cost nothing; the lesson is to get the copy right before the
first submit, not to keep renaming.

Run from project root:
    python -m scripts.create_whatsapp_notification_templates              # submit all five
    python -m scripts.create_whatsapp_notification_templates --dry-run    # print copy, submit nothing
    python -m scripts.create_whatsapp_notification_templates --only aura_tapping_ready
    python -m scripts.create_whatsapp_notification_templates --only aura_tapping_ready,aura_resource_added --replace
"""

import argparse
import time

from app.services.gupshup.client import create_template, delete_template
from app.utils.schema import CreateWhatsappTemplateModel

APP_URL = "https://app.regulatewithaura.com"

# How long --replace waits between deleting a template and resubmitting it. Meta processes the
# delete asynchronously and rejects the new submission until it lands; 90s clears the "under a
# minute" case it reports most often.
DELETE_SETTLE_SECONDS = 90

# Utility TTL ceiling is 12h. A "your session is ready" message that finally lands two days
# later is worse than not landing at all, so the per-user ones take the ceiling; the two
# broadcasts keep WhatsApp's default so an announcement still reaches a phone that was off.
READY_TTL_SECONDS = 43200

FOOTER = "Aura"

TEMPLATES = [
    {
        "env_var": "WA_TEMPLATE_GUIDED_VIZ_READY",
        "payload": {
            "element_name": "aura_visualisation_ready",
            "category": "UTILITY",
            "content": (
                "Hi {{1}}, your guided visualisation is ready 🎧\n\n"
                "It's saved in your Aura library. Find a quiet spot, put your headphones on, "
                "and press play whenever you're ready."
            ),
            "example": (
                "Hi Priya, your guided visualisation is ready 🎧\n\n"
                "It's saved in your Aura library. Find a quiet spot, put your headphones on, "
                "and press play whenever you're ready."
            ),
            "footer": FOOTER,
            "buttons": [{
                "type": "URL",
                "text": "Listen now",
                "url": f"{APP_URL}/visualization?session={{{{1}}}}",
                "example": [f"{APP_URL}/visualization?session=799d9e4b-4721-407b-a9ac-7f622f4474df"],
            }],
            "message_send_ttl_seconds": READY_TTL_SECONDS,
        },
    },
    {
        "env_var": "WA_TEMPLATE_EFT_READY",
        "payload": {
            "element_name": "aura_tapping_ready",
            "category": "UTILITY",
            "content": (
                "Hi {{1}}, your EFT tapping session is ready 🌿\n\n"
                "Your personalised tapping script is saved in your Aura library. Play it whenever "
                "you're ready to move what you're feeling through your body."
            ),
            "example": (
                "Hi Priya, your EFT tapping session is ready 🌿\n\n"
                "Your personalised tapping script is saved in your Aura library. Play it whenever "
                "you're ready to move what you're feeling through your body."
            ),
            "footer": FOOTER,
            "buttons": [{
                "type": "URL",
                "text": "Start tapping",
                "url": f"{APP_URL}/eft-tapping?session={{{{1}}}}",
                "example": [f"{APP_URL}/eft-tapping?session=9fa2b36d-00cd-4a68-a125-ea00fa2216c4"],
            }],
            "message_send_ttl_seconds": READY_TTL_SECONDS,
        },
    },
    {
        "env_var": "WA_TEMPLATE_VISION_BOARD_READY",
        "payload": {
            "element_name": "aura_vision_board_ready",
            "category": "UTILITY",
            "content": (
                "Hi {{1}}, your vision board is ready ✨\n\n"
                "The version of you you're becoming is now on screen. Open it, sit with it for a "
                "minute, and let your body take it in."
            ),
            "example": (
                "Hi Priya, your vision board is ready ✨\n\n"
                "The version of you you're becoming is now on screen. Open it, sit with it for a "
                "minute, and let your body take it in."
            ),
            "footer": FOOTER,
            "buttons": [{"type": "URL", "text": "View vision board", "url": f"{APP_URL}/vision-board"}],
            "message_send_ttl_seconds": READY_TTL_SECONDS,
        },
    },
    {
        "env_var": "WA_TEMPLATE_NEW_MASTERCLASS",
        # {{2}} = masterclass title, {{3}} = start time, already formatted as
        # "Tue, 12 Aug · 7:00 PM IST" by notifications.format_masterclass_time()
        "payload": {
            "element_name": "aura_new_masterclass",
            "category": "UTILITY",
            "content": (
                "Hi {{1}}, a new masterclass has been added to Aura.\n\n"
                "{{2}}\n"
                "🗓 {{3}}\n\n"
                "The joining link and details are on your events page."
            ),
            "example": (
                "Hi Priya, a new masterclass has been added to Aura.\n\n"
                "Letting Go of What No Longer Serves You\n"
                "🗓 Tue, 12 Aug · 7:00 PM IST\n\n"
                "The joining link and details are on your events page."
            ),
            "footer": FOOTER,
            "buttons": [{"type": "URL", "text": "View details", "url": f"{APP_URL}/events"}],
        },
    },
    {
        "env_var": "WA_TEMPLATE_NEW_RESOURCE",
        # {{2}} = category noun ("audio session"), {{3}} = resource name
        "payload": {
            "element_name": "aura_resource_added",
            "category": "UTILITY",
            "content": (
                "Hi {{1}}, a new {{2}} has been added to your Aura library.\n\n"
                "{{3}}\n\n"
                "It's in your resources whenever you need it."
            ),
            "example": (
                "Hi Priya, a new audio session has been added to your Aura library.\n\n"
                "Morning Abundance Meditation\n\n"
                "It's in your resources whenever you need it."
            ),
            "footer": FOOTER,
            "buttons": [{
                "type": "URL",
                "text": "Open it",
                "url": f"{APP_URL}/resources?resource={{{{1}}}}",
                "example": [f"{APP_URL}/resources?resource=6a48d898b766933bb277cf7b"],
            }],
        },
    },
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the copy without submitting anything")
    parser.add_argument("--only", help="comma-separated element_names to submit, instead of all five")
    parser.add_argument("--replace", action="store_true", help="delete the existing template of the same name first — for resubmitting changed copy")
    parser.add_argument("--language", default="en_GB", help="language code to submit under. en_GB by default — the copy is British-spelled, and the en_US slot for several of these names is locked by an earlier deletion")
    args = parser.parse_args()

    names = [t["payload"]["element_name"] for t in TEMPLATES]
    wanted = [n.strip() for n in args.only.split(",")] if args.only else names
    unknown = [n for n in wanted if n not in names]
    if unknown:
        parser.error(f"--only got unknown template(s) {', '.join(unknown)} — must be from: {', '.join(names)}")

    selected = [t for t in TEMPLATES if t["payload"]["element_name"] in wanted]

    env_lines = []
    for template in selected:
        payload = CreateWhatsappTemplateModel(**template["payload"], language_code=args.language)
        print(f"\n=== {payload.element_name} ({payload.category} · {payload.language_code}) ===")
        print(payload.content)
        print(f"[footer] {payload.footer}")
        print(f"[button] {payload.buttons}")

        if args.dry_run:
            continue

        if args.replace:
            # Deleting by elementName is permanent and takes the old id with it. Anything
            # already sent under it is unaffected — this only frees the name to resubmit.
            try:
                delete_template(payload.element_name)
                print(f"--> deleted the existing template of this name · waiting {DELETE_SETTLE_SECONDS}s for Meta to process it")
                time.sleep(DELETE_SETTLE_SECONDS)
            except Exception as e:
                print(f"--> nothing to delete ({getattr(e, 'detail', e)})")

        try:
            result = create_template(payload)
            template_id = (result.get("template") or {}).get("id", "")
            status = (result.get("template") or {}).get("status", "")
            print(f"--> submitted · status={status} · id={template_id}")
            env_lines.append(f"{template['env_var']}={template_id}")
        except Exception as e:
            # Keep going: one rejected template (usually a category disagreement) shouldn't
            # block the other four from being submitted.
            print(f"--> FAILED: {e}")

    if env_lines:
        print("\nAdd these to .env / the deploy secrets once Meta approves them:\n")
        print("\n".join(env_lines))


if __name__ == "__main__":
    main()
