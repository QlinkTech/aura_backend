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

              <p style="margin:0 0 24px 0;font-size:20px;color:#1a1a1a;font-weight:600;">Welcome to Aura ✨</p>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                We're so happy you're here.
              </p>

              <p style="margin:0 0 16px 0;font-size:16px;color:#555555;line-height:1.8;">
                Aura works best when you use it like a real support system, not just another app you scroll through once and forget about. So here's a simple guide to help you begin.
              </p>

              <p style="margin:0 0 12px 0;font-size:16px;color:#555555;line-height:1.8;font-weight:600;">We recommend starting like this:</p>

              <ul style="margin:0 0 24px 0;padding-left:20px;font-size:16px;color:#555555;line-height:2;">
                <li>Open Miss Aura and start with whatever feels most emotionally present for you right now. Don't worry about asking the "perfect" question.</li>
                <li>Use Aura in real moments. During overwhelm, emotional spirals, confusion, burnout, self-doubt, relationship stress, business stress, anxiety, or when you simply need grounding and clarity.</li>
                <li>Explore the different tools inside the platform slowly. Try the journaling prompts, EFT tapping, nervous system exercises, visualisations, regulation practices, and mindset rewiring tools based on what feels aligned to you that day.</li>
                <li>The more honestly and consistently you engage, the more personalised and supportive your experience becomes over time.</li>
                <li>You do not need to consume everything at once. This is a space you return to, not race through.</li>
              </ul>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                We're building Aura very intentionally, and your feedback genuinely matters to us.
              </p>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                If you face any technical issues, login or payment concerns, confusion while using the platform, or if something doesn't feel smooth, please reply to this email and our team will help you out.
              </p>

              <p style="margin:0 0 36px 0;font-size:16px;color:#555555;line-height:1.8;">
                And if there's something you love, something you wish existed inside Aura, or a moment where the platform genuinely helped you, we would LOVE to hear from you too. Your feedback helps us make Aura better for every woman inside this space.
              </p>

              <p style="margin:0 0 24px 0;font-size:16px;color:#555555;line-height:1.8;">
                Thank you for being here.
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
                You're receiving this email because you created an account on Aura.<br/>
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
