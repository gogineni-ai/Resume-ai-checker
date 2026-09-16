# Gmail verification email sender

The default email provider remains Resend until Gmail is connected and explicitly enabled.

Configure these backend environment variables through Render's secret settings:

- `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`: the Google web application client.
- `GMAIL_SENDER_EMAIL`: the account that will authorize sending.
- `GMAIL_ADMIN_EMAIL`: an existing, verified Resume Verifier administrator account.
- `GMAIL_ENCRYPTION_KEY`: a Fernet key, kept stable across deployments. Losing or changing it requires reconnecting the sender.
- `AUTH_SECRET`: a strong random application signing secret of at least 32 characters. The Gmail admin routes reject the development default.
- `GMAIL_REDIRECT_URI`: the backend origin followed by `/api/admin/gmail/callback`, exactly matching the Google client redirect URI.

Enable Gmail API for the Google project. For an external app in Testing, add the sender as a test user. Test-mode Google refresh tokens for Gmail access normally expire after seven days; this is not a permanent unattended delivery setup. Complete Google's production requirements before relying on it long term.

Sign in as the configured verified administrator, visit `/settings/email` on the frontend, and choose Connect Gmail. Authorize the configured sender with email identity and Gmail send permission. The callback verifies the sender, consumes a ten-minute single-use state, exchanges a PKCE-protected authorization code, and stores the refresh token encrypted in the database.

After successful connection, set `EMAIL_PROVIDER=gmail` and verify actual OTP delivery to a different recipient. The connected status alone does not prove delivery. Reconnect if authorization expires or is revoked. Never commit credentials or paste tokens into chat.

The application suppresses callback access log entries; upstream proxy logging is controlled separately by the hosting platform.
