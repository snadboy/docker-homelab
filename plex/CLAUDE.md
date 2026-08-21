# Topic: plex

Working directory for a Remote Control topic session covering media serving,
transcoding, and library health. Most work here is API and SSH against running
services, not editing this compose file.

## Skills
`/plex` · `/plex-audit` · `/plex-dedup` · `/plex-add-stereo` · `/tautulli` ·
`/dsm-disk-report`

## Never do this
- **Don't restart Plex or run `/gpu-benchmark` while streams are active.** Check for
  active sessions first — the benchmark saturates the iGPU used for transcoding.
- **Don't delete media directly on the NAS.** The *arr apps lose track of it and will
  re-grab. Go through `/plex-dedup` or Maintainerr.

<!-- Host-specific state lives in plex/CLAUDE.local.md (gitignored). -->
