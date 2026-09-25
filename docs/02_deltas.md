# Changes from the supplied revision

Version 0.2 was a design and selected synthetic fixture checker. Version 0.3 adds executable compiler, adapter, resolver, qualification/trust services, transactional reference backend, explicit legacy bridge, replay and operating tools.

The original 42 tests remain unchanged. The compatibility fixture adds immutable claim content and stronger root/source contracts. All 18 review probes are rerun against that surface. The runtime uses a new versioned record envelope rather than silently changing the meaning of old observations. No old observation is converted into an authenticated live result.

Observations no longer contain mutable policy evaluations. A policy change appends a distinct evaluation branch and leaves observation identities unchanged. Generic mutations become six discriminated variants. One authoritative lifecycle replaces conflicting status vocabularies. Complete-run verification now differs explicitly from partial drafts, and signed roots are distinct from locally rehashable chains.

See `13_recommendation_traceability.md` for individual review findings and the release validation report for measured outcomes.
