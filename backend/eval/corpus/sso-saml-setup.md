# Setting up single sign-on with SAML

Single sign-on lets members log in through your company identity provider instead of with a separate Acme Cloud password. It is available on the Business and Enterprise plans, and only workspace owners can configure it.

Before you start, have your identity provider's metadata URL or XML file ready. Supported providers include Okta, Microsoft Entra ID, Google Workspace and any provider that speaks SAML 2.0.

1. Open Settings, Security, Single sign-on and choose Set up SAML.
2. Copy the Acme Cloud values shown on screen: the entity ID, the assertion consumer service (ACS) URL and the certificate fingerprint. Paste them into a new application in your identity provider.
3. In your identity provider, map the NameID to the member's email address. Optionally map first name, last name and group claims.
4. Back in Acme Cloud, upload the metadata file or paste the metadata URL, then press Test connection.
5. When the test succeeds, enable Require SSO for all members. Members who already have passwords keep them until you switch enforcement on.

Always keep one owner account that can still log in with a password. If the identity provider is misconfigured and enforcement is on, that account is the only way back in. When login fails, see the SSO error reference.
