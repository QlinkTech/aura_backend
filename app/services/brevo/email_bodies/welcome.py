def get_welcome_email_html(name: str = "") -> str:
    greeting = f"Hi {name}," if name else "Hi,"
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

              <p style="margin:0 0 8px 0;font-size:20px;color:#1a1a1a;font-weight:600;">Welcome to The Aura &#x1F90D;</p>

              <p style="margin:16px 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                We're really glad you're here.
              </p>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                You've just stepped into a space designed to support you — not overwhelm you.<br/>
                A place where you don't have to figure everything out on your own.
              </p>

              <p style="margin:0 0 12px 0;font-size:16px;color:#1a1a1a;font-weight:600;">Inside The Aura, you'll have:</p>

              <table cellpadding="0" cellspacing="0" style="margin:0 0 24px 0;width:100%;">
                <tr>
                  <td style="padding:8px 0;font-size:15px;color:#555555;line-height:1.7;">
                    &bull;&nbsp;&nbsp;Ongoing access to guidance when you need clarity, reflection, or direction
                  </td>
                </tr>
                <tr>
                  <td style="padding:8px 0;font-size:15px;color:#555555;line-height:1.7;">
                    &bull;&nbsp;&nbsp;Tools to regulate your nervous system and feel more steady day to day
                  </td>
                </tr>
                <tr>
                  <td style="padding:8px 0;font-size:15px;color:#555555;line-height:1.7;">
                    &bull;&nbsp;&nbsp;Resources to support manifestation, growth, and aligned decision-making
                  </td>
                </tr>
                <tr>
                  <td style="padding:8px 0;font-size:15px;color:#555555;line-height:1.7;">
                    &bull;&nbsp;&nbsp;A space that meets you where you are — without pressure or performance
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                Think of The Aura as a quiet, reliable presence in your life —<br/>
                one that helps you pause, process, and move forward with more clarity and ease.
              </p>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                We'll be rolling out features gradually starting <strong style="color:#1a1a1a;">1st April</strong>, so you'll see new experiences, tools, and updates coming your way over time. We'll keep you informed every step of the way.
              </p>

              <p style="margin:0 0 28px 0;font-size:16px;color:#555555;line-height:1.8;">
                For now, take your time. Explore at your own pace.
              </p>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" style="margin:0 0 36px 0;">
                <tr>
                  <td style="border-radius:8px;background-color:#1a1a1a;">
                    <a href="https://app.manifestwithaura.com/" target="_blank"
                       style="display:inline-block;padding:14px 32px;font-size:15px;color:#ffffff;text-decoration:none;letter-spacing:1px;font-family:'Georgia',serif;">
                      Enter The Aura
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 8px 0;font-size:16px;color:#555555;line-height:1.8;">We're really happy you're here.</p>
              <p style="margin:0 0 4px 0;font-size:16px;color:#555555;line-height:1.8;">Warmly,</p>
              <p style="margin:0;font-size:16px;color:#1a1a1a;font-weight:600;">Team Aura</p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color:#f9f7f4;padding:24px 48px;text-align:center;border-top:1px solid #eeeeee;">
              <p style="margin:0;font-size:12px;color:#aaaaaa;line-height:1.6;">
                You're receiving this email because you joined The Aura early bird program.<br/>
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
