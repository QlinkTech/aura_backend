def get_welcome_email_html(name: str = "") -> str:
    first_name = name.strip().split()[0] if name.strip() else ""
    greeting = f"Hi {first_name}," if first_name else "Hi,"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Welcome to The Aura</title>
</head>
<body style="margin:0;padding:0;background-color:#f9f7f4;font-family:'Georgia',serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f9f7f4;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:12px;overflow:hidden;max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="background-color:#1a1a1a;padding:36px 48px;text-align:center;">
              <p style="margin:0;font-size:26px;color:#ffffff;letter-spacing:4px;font-weight:400;">THE AURA</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:48px 48px 32px 48px;">
              <p style="margin:0 0 24px 0;font-size:16px;color:#333333;line-height:1.8;">{greeting}</p>

              <p style="margin:0 0 24px 0;font-size:20px;color:#1a1a1a;font-weight:600;">You're officially a part of Aura ✨</p>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                Your subscription is confirmed and you now have <strong style="color:#1a1a1a;">complete access</strong> to everything inside Aura.
              </p>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                This is your space — to come back to as often as you need, in the moments that matter most. We're honoured you chose Aura as part of your support system.
              </p>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                If you ever face any technical issues, payment concerns, or anything that doesn't feel smooth, simply reply to this email and our team will be right there.
              </p>

              <p style="margin:0 0 36px 0;font-size:16px;color:#555555;line-height:1.8;">
                Thank you for investing in yourself. We don't take that lightly.
              </p>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" style="margin:0 0 40px 0;">
                <tr>
                  <td style="border-radius:8px;background-color:#1a1a1a;">
                    <a href="https://app.regulatewithaura.com/" target="_blank"
                       style="display:inline-block;padding:14px 32px;font-size:15px;color:#ffffff;text-decoration:none;letter-spacing:1px;font-family:'Georgia',serif;">
                      Enter The Aura
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 4px 0;font-size:16px;color:#555555;line-height:1.8;">With love,</p>
              <p style="margin:0;font-size:16px;color:#1a1a1a;font-weight:600;">Team Aura ✨</p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color:#f9f7f4;padding:24px 48px;text-align:center;border-top:1px solid #eeeeee;">
              <p style="margin:0;font-size:12px;color:#aaaaaa;line-height:1.6;">
                You're receiving this email because you subscribed to Aura.<br/>
                &copy; 2025 Aura. All rights reserved.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
