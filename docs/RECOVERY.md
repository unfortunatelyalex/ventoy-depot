# Recovery

- A `.partial` file is never a completed ISO and can be removed after Ventoy Depot is
  closed. The application removes it automatically after handled failures.
- A `.download` file in the configured cache can be retained for a validated HTTP
  resume. Its ETag or Last-Modified validator is stored beside it.
- Explicitly replaced images are moved to `.ventoy-depot/trash`. Move the desired file
  back to its original directory while Ventoy Depot is not writing to the drive.
- Never rename an unverified `.partial` or `.download` file to `.iso`.
- If a drive was removed during copying, reconnect it, run `ventoy-depot verify PATH`,
  remove stale `.partial` files, and build a fresh plan.
