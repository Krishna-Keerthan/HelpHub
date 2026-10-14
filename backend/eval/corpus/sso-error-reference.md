# Single sign-on error reference

When SAML login fails, Acme Cloud shows an error code on the sign-in page. Codes beginning with E-40 relate to the assertion your identity provider sends.

| Code | Meaning | Usual fix |
|---|---|---|
| E-4011 | The ACS URL in the response does not match the one we expect | Re-copy the ACS URL into the identity provider |
| E-4012 | Assertion signature invalid: the signing certificate does not match the fingerprint stored for your workspace | Upload the current certificate in Settings, Security, Single sign-on |
| E-4013 | Assertion expired or not yet valid: the clocks of the identity provider and Acme Cloud differ by more than five minutes | Synchronise the identity provider's server time (NTP), then retry |
| E-4014 | The NameID is missing or is not an email address | Map NameID to the user's email |

E-4012 and E-4013 look similar but have different causes. E-4012 is about trust, a certificate that was rotated or copied incorrectly. E-4013 is about time. Do not rotate certificates to fix E-4013, and do not adjust clocks to fix E-4012.

If members see E-4012 right after your identity provider renewed its certificate, upload the new metadata file. Old and new certificates can be active together for up to 30 days so that logins keep working during the change.
