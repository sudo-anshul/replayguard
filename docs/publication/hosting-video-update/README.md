# Static demo-link deployment verification

Amplify **Deployment 3** published the exact 24-asset ZIP to the existing `prod` site. The [console observation](hosting-deployment-video-update.json) records “Deployed” and “Deployment SUCCEED,” with a displayed seven-second duration. It is UI evidence; no CLI/API deployment response is claimed. [Deployment 2 records](../hosting-final/hosting-deployment-final.json) remain unchanged.

The [independent anonymous HTTPS check](anonymous-https-video-update.json) passed for the root and all 24 assets. Every SHA-256 matches the [staged manifest](site-stage-manifest.json), and the root, `index.html` and `repair.html` link to `CGE19upS66A` with the superseded video ID absent. [The upload bundle record](site-upload-bundle.json) preserves the ZIP size, hash and asset hashes. The deployed root-page footer link was also confirmed through the browser. This verifies public site bytes and links; it does not claim a rendered interaction review, signed-out YouTube playback or a new AWS fault experiment.

To repeat the read-only check after a confirmed deployment, use Python 3 with a trusted CA store:

```sh
python3 docs/publication/hosting-video-update/verify_anonymous_https.py --deployment-job-id 3
```

The recorded run used the operating system's root CA bundle through `SSL_CERT_FILE=/etc/ssl/cert.pem` because this Python installation had no default CA store. Certificate and hostname verification stayed enabled. The script uses no AWS credentials, authentication, cookies or proxy, follows no redirects, and makes one bounded request for each of 25 URLs.
