# Provenance and reuse

This is a new maintenance facade and Skill, not a new gameplay framework and not a Doxygen C++ fork.

`doxygenue/` retains the source slicing, CPP/H pairing, Doxygen XML projections, function diff, quality checking, locks and transaction code from the 0.3.0 package supplied in this conversation, with its supplied reuse-regression patch. It is not separately exposed as an MCP endpoint in this package. The old GUI/server/installation layer is not copied.

`maintenance/`, the new GUI/server, record adapters, editor-only bridge, task profiles, Skill and task acceptance are this delivery's implementation. Source-engine provenance and changes are recorded in MANIFEST.json/UPSTREAM.json. Existing copyright notices are retained. No license is invented for the user's prior code; choose the repository license before publishing.

Doxygen executable/source and font files are NOT bundled. Optional Windows runtime bootstrap retrieves a fixed official release and verifies its supplied SHA256. Doxygen's own package includes its license. The Linux CI binary used during tests is not redistributed here.

No Unity/Unreal runtime module, Tick manager, gameplay database, object registry or data-source replacement is installed in a game. `examples/ExistingProject` is a native C++ + data fixture with UE-layout metadata, not a playable Unreal project. Editor contract tests use test doubles kept in tests only, never shipping fallback implementations.
