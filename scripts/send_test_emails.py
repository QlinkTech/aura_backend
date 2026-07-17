"""
Send one of every transactional email through Resend, to verify templates,
sender identity and Reply-To after the Brevo -> Resend migration.

Sends real email. Point --to at an inbox you own.

Run from project root:
    python -m scripts.send_test_emails                      # send to the default test inbox
    python -m scripts.send_test_emails --to you@example.com # send somewhere else
    python -m scripts.send_test_emails --dry-run            # print payloads, send nothing
"""

import argparse
import resend
from app.services.mail import client

DEFAULT_TO = "prathampersonal0@gmail.com"
TEST_NAME = "Pratham"
TEST_RESET_LINK = "https://regulatewithaura.com/reset-password?token=test-token-123"


def build_cases(to: str):
    """Every send_* wrapper in the mail client, with the args it needs."""
    return [
        ("welcome",               lambda: client.send_welcome_email(to_email=to, to_name=TEST_NAME)),
        ("account_created",       lambda: client.send_account_created_email(to_email=to, to_name=TEST_NAME)),
        ("thank_you",             lambda: client.send_thank_you_email(to_email=to, to_name=TEST_NAME)),
        ("vision_board_ready",    lambda: client.send_vision_board_ready_email(to_email=to, to_name=TEST_NAME)),
        ("subscription_cancelled", lambda: client.send_subscription_cancelled_email(to_email=to, to_name=TEST_NAME)),
        ("trial_ended",           lambda: client.send_trial_ended_email(to_email=to, to_name=TEST_NAME)),
        ("reset_password",        lambda: client.send_reset_password_email(to_email=to, to_name=TEST_NAME, reset_link=TEST_RESET_LINK)),
    ]


def install_dry_run_stub():
    """Swap the network call for a printer, so --dry-run exercises everything but the send."""
    def fake_send(params, **kwargs):
        print(f"    from     : {params['from']}")
        print(f"    to       : {params['to']}")
        print(f"    subject  : {params['subject']}")
        print(f"    reply_to : {params['reply_to']}")
        print(f"    html     : {len(params['html'])} bytes")
        return {"id": "dry-run-no-id"}
    resend.Emails.send = fake_send


def main():
    parser = argparse.ArgumentParser(description="Send every transactional email via Resend")
    parser.add_argument("--to", default=DEFAULT_TO, help=f"recipient (default: {DEFAULT_TO})")
    parser.add_argument("--dry-run", action="store_true", help="print payloads without sending")
    args = parser.parse_args()

    if not resend.api_key:
        raise SystemExit("RESEND_API_KEY is not set — check your .env")

    if args.dry_run:
        install_dry_run_stub()

    mode = "DRY RUN — nothing will be sent" if args.dry_run else "SENDING REAL EMAIL"
    cases = build_cases(args.to)
    print(f"{mode}\nto       : {args.to}\nfrom     : {client.SENDER}\nreply-to : {client.REPLY_TO_EMAIL}\n")

    sent, failed = 0, 0
    for name, send in cases:
        try:
            result = send()
            print(f"  [ok]   {name:24s} id={result.get('id')}")
            sent += 1
        except Exception as e:
            print(f"  [FAIL] {name:24s} {e}")
            failed += 1

    print(f"\n{sent}/{len(cases)} sent, {failed} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
