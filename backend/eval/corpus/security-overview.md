# Security overview

Security at Acme Cloud rests on a few simple principles: encrypt everything, give people the least access they need, and keep a record of what happened.

Encryption. Data is encrypted in transit with TLS 1.2 or newer and at rest with AES-256. Encryption keys are stored in a dedicated key management service and rotated every year. Enterprise customers can bring their own key.

Infrastructure. Workspaces are hosted in the region you pick at sign-up: United States, European Union or Asia-Pacific. Data stays in that region, including backups. Backups are taken every hour and kept for 35 days.

Access control. Staff cannot open customer files. Support engineers can see metadata such as file names only after the owner approves a time-limited support access request in Settings, Security.

Authentication. We support two-factor authentication, hardware keys and single sign-on. Passwords are stored as salted hashes.

Compliance. Acme Cloud holds SOC 2 Type II and ISO 27001 certificates, and offers a data processing agreement for GDPR. Reports are available under NDA from the trust page.

Vulnerability reports. Researchers can write to the security team; we answer within two business days and do not take legal action against good-faith reports. Penetration tests by independent firms are carried out twice a year.

Incidents. If personal data is affected we notify the owner within 72 hours.
