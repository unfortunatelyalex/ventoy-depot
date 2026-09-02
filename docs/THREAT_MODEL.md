# Threat model

Ventoy Depot treats provider metadata, networks, filenames, removable media and local
manifests as untrusted. Its security objective is to prevent an unverified artifact or
partial copy from becoming a bootable-looking final ISO, and to avoid silently changing
the user's chosen product variant.

Controls include HTTPS-only allow-listed hosts with redirect and public-address checks;
bounded metadata and downloads; SHA-256/SHA-512 verification; optional OpenPGP
verification against a dedicated keyring and full pinned fingerprints; mountpoint path
containment; repeated device checks; `.download`/`.partial` staging; fsync and atomic
rename; and recoverable replacement through `.ventoy-depot/trash`.

Out of scope are a compromised upstream signing key, malicious firmware, an already
compromised operating system, physical attacks during a write, and media corruption
after the completed copy verification. Users should keep offline recovery media and
independently protect any registry signing keys.

Remote declarative registry data is not enabled until the separately signed registry
and its initial TUF root metadata have been provisioned. Local manifests contain no
executable code and must be explicitly enabled by the user.
