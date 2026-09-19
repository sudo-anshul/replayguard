# Public source preparation

Publication was resumed by the user on September 19, 2026. The public source
tree was extracted from the audited local source ZIP with SHA-256
`6f2b23800d1eb67e79a60aea13aa0a70d6948b45ed9212317a2d556b861a1a17`.
Public-facing documentation was then updated, and offline CI was added.
The first public commit uses its actual creation date. The private development
repository's Git history is not part of this repository.

The original snapshot manifest is retained under [source-snapshot/](source-snapshot/).
It describes the earlier ZIP, not the changed public Git tree. Existing ZIPs,
recorded AWS evidence and video bytes were preserved during publication.

Before publication, a separate agent inspected the stable source tree and 76
entries inside the three downloadable ZIPs for denied private paths and common
credential/private-key patterns. It found no publish-blocking issue. A marker
in the evidence-redaction unit test was synthetic test input, not a credential.
That bounded audit is not a guarantee that every possible secret format was
recognized. Account configuration, private research and private Git history
were excluded by the source allowlist.

CI runs the standard-library repair tests, source-export checks, JavaScript
contracts, the independently frozen application transfer and the explicit
unresolved control. It needs no AWS account, credentials, network service or
package installation after the source checkout. CI does not deploy the lab.
Some retained historical browser/media scripts require original workspace
artifacts; the documented offline commands are the self-contained checks.

See [current publication status](../publication-status.md) for confirmed
repository, hosting, video and submission links.

The [initial hosting verification](hosting-initial/anonymous-https-initial.json) records anonymous HTTPS byte checks for the deployed static assets. [Deployment](hosting-initial/hosting-deployment-initial.json) and [minimal hosting configuration](hosting-initial/hosting-configuration-initial.json) omit signed upload URLs and credentials. These facts do not claim a new failure experiment.

The [final hosting summary](hosting-final/hosting-public-summary-final.json) and [anonymous HTTPS checks](hosting-final/anonymous-https-final.json) verify deployment job 2, including the published Source/Demo footer links. The [initial hosted-CI observation](github-ci-initial.json) records a runner that never started and the separate passing local checks.

The [final browser review](browser-review.json) records the observed desktop/narrow layouts and interaction states. The [YouTube publication record](youtube-publication.json) records the unlisted video, playable signed-in watch page, published English transcript and saved resource links; signed-out playback remains unverified.
