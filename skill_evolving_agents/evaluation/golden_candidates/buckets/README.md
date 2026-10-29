# Candidate access buckets

Every candidate is assigned one primary bucket. A skill can also require
auth or payment while sitting in `needs_app_or_env`; the flags are in each
`metadata.json` under `access`.

| Bucket | Count | Resource need | Human intervention |
|---|---:|---|---|
| [needs_app_or_env](needs_app_or_env/INDEX.md) | 87 | Requires an installed app, specialized runtime, lab, hardware, browser automation, or cloud environment. May also need auth/payment. | install_or_provision_env, admin_setup, manual_review |
| [needs_signin_and_payment](needs_signin_and_payment/INDEX.md) | 1 | Requires an account with a paid plan or paid API entitlement. No specialized local app assumed. | create_account, billing, mfa, admin_consent, manual_review |
| [needs_signin](needs_signin/INDEX.md) | 3 | Requires an account/login, but no payment is assumed. Free tier or existing test account may be sufficient. | create_account, mfa, session, manual_review |
| [no_signin](no_signin/INDEX.md) | 75 | Local files, code, analysis, writing, or artifact generation. No account or paid service assumed. | manual_review |
