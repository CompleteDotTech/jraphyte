# V7 application boundary

The V6 public-module enrollment pin is withdrawn: it cycled with the
successor plan's code identity because enrollment contains the plan SHA.
The generic `execute_successor` API now requires the exact concrete
`RootEnrolledConverterApplication` class. It does not offer a CLI effect path.

An externally reviewed root-owned private launcher, kept outside the public
method-hash closure, must pin the exact approved application release path and
SHA. Its release binds the enrollment SHA, old immutable inventory,
reconciliation authority/receipt, source checkout, and distinct successor
plan/output. The launcher in the companion D task directory is disabled with
both pins unset. A separately reviewed versioned launcher and release are
required before any real effect.

The collector itself remains Docling-only and fails closed on missing Python
process image, command line, or creation time. The historical old result
remains `UNKNOWN_UNATTESTED_NO_RETRY`. No converter has run under this version.
