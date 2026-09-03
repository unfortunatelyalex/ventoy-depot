# Recovery

- A `.partial` file is never a completed ISO and can be removed after Ventoy Depot is
  closed. The application removes it after handled failures only when it can confirm that
  the same Ventoy device is still mounted; after removal or replacement of the drive, clean
  up the original device manually when it is safely reconnected.
- A `.download` file in the configured cache can be retained for a validated HTTP
  resume. Its ETag or Last-Modified validator is stored beside it.
- Explicitly replaced images are moved to `.ventoy-depot/trash`. Move the desired file
  back to its original directory while Ventoy Depot is not writing to the drive.
- If an interruption happens after the old same-named ISO was moved but before the new
  ISO was published, the verified new file may remain as `<name>.partial` and the prior
  image remains in `.ventoy-depot/trash`. Do not promote the partial file manually. With
  Ventoy Depot closed, move the prior image back to its original directory, then create a
  fresh update plan.
- Never rename an unverified `.partial` or `.download` file to `.iso`.
- If a drive was removed during copying, reconnect it, run `ventoy-depot verify PATH`,
  remove stale `.partial` files, and build a fresh plan.
