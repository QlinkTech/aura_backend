def get_thank_you_email_html(name: str = "") -> str:
    greeting = f"Hi {name}," if name else "Hi,"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Thank You — The Aura</title>
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

              <p style="margin:0 0 20px 0;font-size:20px;color:#1a1a1a;font-weight:600;">Thank you for your support &#x1F90D;</p>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                Your payment has been received and your subscription is active.
              </p>

              <p style="margin:0 0 28px 0;font-size:16px;color:#555555;line-height:1.8;">
                We're grateful you're choosing to invest in yourself this way.<br/>
                The Aura is here whenever you need it — to help you slow down, get clear, and move forward.
              </p>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" style="margin:0 0 36px 0;">
                <tr>
                  <td style="border-radius:8px;background-color:#1a1a1a;">
                    <a href="https://app.manifestwithaura.com/" target="_blank"
                       style="display:inline-block;padding:14px 32px;font-size:15px;color:#ffffff;text-decoration:none;letter-spacing:1px;font-family:'Georgia',serif;">
                      Open The Aura
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 4px 0;font-size:16px;color:#555555;line-height:1.8;">Warmly,</p>
              <p style="margin:0;font-size:16px;color:#1a1a1a;font-weight:600;">Team Aura</p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color:#f9f7f4;padding:24px 48px;text-align:center;border-top:1px solid #eeeeee;">
              <p style="margin:0;font-size:12px;color:#aaaaaa;line-height:1.6;">
                You're receiving this email because you have an active Aura subscription.<br/>
                &copy; 2025 The Aura. All rights reserved.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
