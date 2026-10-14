# Two-factor authentication

Two-factor authentication (2FA) asks for a second proof of identity when you sign in. Even if someone learns your password, they cannot enter your account without the second factor.

Supported methods
- Authenticator app. Any app that supports time-based one-time passwords works. Codes change every 30 seconds.
- Hardware security key. Keys that support the FIDO2 standard are accepted. Acme Cloud sells a compatible key as SKU CD-7781-M, packed in pairs so you always have a spare.
- SMS codes are available but not recommended, because phone numbers can be taken over by attackers. Owners can disable SMS for the whole workspace.

Turning it on
1. Open your profile, Security, Two-factor authentication.
2. Choose a method and follow the on-screen steps.
3. Save the ten backup codes somewhere safe, for example in a password manager. Each works once.

Requiring 2FA. Owners can require two-factor for all members in Settings, Security. Members without it are asked to set it up at their next sign-in and get a grace period of seven days.

Trusted devices. After a successful sign-in you can mark a browser as trusted for 30 days. Signing out from every device removes all trusted devices. Members using single sign-on follow the second-factor rules of their identity provider.
