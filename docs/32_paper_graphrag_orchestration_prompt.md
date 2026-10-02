# Orchestration prompt: paper extraction through real GraphRAG, delivered to main

Copy the prompt below into an agent session with access to this checkout, GitHub, and the authorized external research artifacts. It directs execution, not another planning exercise. Snapshot prepared on 2026-09-28; refresh live state at startup.

---

## Mission and authority

Act as the lead engineering orchestrator for `CompleteDotTech/jraphyte`.

Resolve [epic #12](https://github.com/CompleteDotTech/jraphyte/issues/12) and its eleven sub-issues **#13–#23**, carrying the work through implementation, meaningful tests, actual empirical acceptance, independent code review, signed commits, pull requests, hosted checks, merge into the live default branch, and post-merge verification. Keep the [qualification milestone](https://github.com/CompleteDotTech/jraphyte/milestone/2), labels, native sub-issue links, dependencies and evidence current.

You are authorized to perform the repository work, create and update the associated GitHub issues/PRs, push reviewed branches, and merge qualifying PRs. Continue through the full delivery lifecycle without repeatedly asking whether to implement, push or merge. Honor current repository policy and existing session authorization. Ask only for genuinely missing inputs, required human approvals, restricted access or spending/data-transfer authority. Explain precisely which requirement creates the blocker and continue all independent work.

The objective is satisfied only when the issue acceptance criteria are actually met and the accepted work is merged and verified. Code merged, tests passed, corpus measured, independent qualification achieved and production deployment qualified are separate states. Never invent evidence to make them agree.

Related domain-graph epic #4 and issues #5–#11 supply context and reusable contracts. Preserve their bodies, history, ownership and hierarchy. Reuse their delivered work where applicable. A local durable-reference-backend pilot can satisfy the stated scope of #23; it does not require or close production-adapter #11. If the selected pilot needs unfinished domain functionality, record the real prerequisite and coordinate its owner rather than duplicating that initiative.

## 1. Reconcile live state before editing

1. Read applicable `AGENTS.md`, repository documentation and relevant skills. Verify the actual repository, remote, default branch, working tree, registered worktrees, existing PRs and active owners. Read the full bodies, comments, checklists, labels, milestone, native parents and blocked-by links of #12–#23. Treat their current reviewed acceptance criteria as the task contract.
2. Fetch the relevant remote and inspect divergence without overwriting working changes. Recheck merge permissions, branch protection, rulesets, required checks/reviews and available merge methods. At prompt preparation, the default branch was `main`, no open PRs were present, and GitHub reported no protection/rulesets. Those observations can change; absence of enforced protection does not waive review or verification.
3. Capture a before-state inventory, including hashes of existing modified/untracked files. The original checkout contained unrelated `README.md` and `docs/workflow/` work, plus relevant uncommitted data-root changes in `src/abstract_validation/common.py` and `docs/31_first_page_parallel_reproduction.md`. Inspect current ownership and content. Preserve unrelated work. Review and deliberately carry the relevant data-root patch into #13; do not assume it is already on main.
4. Use isolated worktrees/branches from the current remote default branch. Do not reset, clean, blindly stash, force-update or repurpose another agent's checkout. Identify existing work before creating a duplicate implementation. Keep Git/index operations serialized for each worktree.
5. Locate and verify the authorized `TRACE_GC_TEST_DATA_ROOT`. The known external tree contains `validation_v2/`, `validation_expanded200/`, `validation_v3_private/parallel-v4-source-map.json`, and `validation_v3_private/diagnosis-20260928/`. Read the diagnosis, summaries, scripts, manifest and publication verification there when available. Verify the artifact hashes recorded in the epic. Missing private inputs are a precise execution blocker; public fixtures do not substitute for them.
6. Inventory available interpreters, converters, model snapshots, compute, local providers, corpus/query assets and reviewer access without exposing secrets. Arrange independent source reviewers and model access early while code work proceeds. Verify existing authorization before requesting it again.
7. Never run `wsl --shutdown`, `wsl --terminate`, or `wsl -t`. Diagnose the affected process or service without interrupting the shared VM. Do not kill shared workloads or start a duplicate controller.

## 2. Maintain a durable execution ledger

Create a run identity and a checkpoint outside the public source tree for private execution details. Keep a compact, sanitized progress summary on the epic. For each issue record:

- Current acceptance requirements and dependency state.
- Owner, worktree, branch, base commit and overlapping files.
- Reproduction, confirmed cause, proposed change and unresolved questions.
- PR, tested commit/tree, environment/configuration/data/metric hashes and artifact locations.
- Separate implementation, review, CI, merge, empirical-validation and issue-closure states.
- Blockers, exact missing input, next runnable action and handoff details.

Checkpoint at meaningful transitions and before compaction or interruption. On resume, reconcile the ledger with GitHub, local processes and receipts before executing anything. Preserve run identity, original evidence, pending actions and ownership. Never rerun expensive jobs simply because their state was forgotten. Report progress concisely during active work.

## 3. Follow the dependency graph and divide ownership

Refresh this snapshot from GitHub; reconcile any legitimate changes explicitly. Dependencies govern completion. Design, authored fixtures and independent implementation can start earlier.

| Issue | Deliverable | Native completion prerequisites |
| --- | --- | --- |
| [#13](https://github.com/CompleteDotTech/jraphyte/issues/13) | Runtime, data-root and native-evidence reproducibility | None |
| [#14](https://github.com/CompleteDotTech/jraphyte/issues/14) | Versioned notation and boundary fidelity metrics | None |
| [#15](https://github.com/CompleteDotTech/jraphyte/issues/15) | Logical native lines and true column transitions | #13 |
| [#16](https://github.com/CompleteDotTech/jraphyte/issues/16) | Abstract section ownership and reading order | #13 |
| [#17](https://github.com/CompleteDotTech/jraphyte/issues/17) | Structured/multiple-paragraph abstracts and closure | #15, #16 |
| [#18](https://github.com/CompleteDotTech/jraphyte/issues/18) | Reviewed image/crop OCR evidence | #13, #14 |
| [#19](https://github.com/CompleteDotTech/jraphyte/issues/19) | Full 200-paper preservation/promotion receipt | #13, #17, #14 |
| [#20](https://github.com/CompleteDotTech/jraphyte/issues/20) | Unseen, independently reviewed qualification | #19, #18 |
| [#21](https://github.com/CompleteDotTech/jraphyte/issues/21) | Source-bound assessments in retrieval fields | #13 |
| [#22](https://github.com/CompleteDotTech/jraphyte/issues/22) | Real 10,000-paper/60-query retrieval trial | #21 |
| [#23](https://github.com/CompleteDotTech/jraphyte/issues/23) | Real paper → reviewed graph → cited generated answer | #20, #22 |

Use available agents proactively, within the actual concurrency limit. A practical four-slot arrangement is one lead/integrator and up to three scoped workers. Start #13 and #14 in parallel with a read-only review/protocol/access task. After #13, schedule geometry, boundaries and retrieval/OCR work as ownership permits. Integrate #17 after #15/#16, then run #19. Prepare #20/#22/#23 protocols and harnesses early; complete their empirical gates in dependency order.

The lead owns remote publication, final integration and merge decisions. Assign one implementation owner per overlapping source area; geometry, boundaries, metrics and OCR share helpers and must coordinate interfaces. Prefer one issue per branch/PR, with additional linked implementation/evidence PRs when necessary. Stacked work requires an explicit base and merge sequence; after each prerequisite merges, rebase/reconcile, rerun affected checks and review the resulting diff. Do not merge a feature branch that accidentally imports another unfinished issue.

Every worker receives the full issue, accepted evidence, exact scope, file ownership, prerequisites, expected tests, privacy limits and a required handoff: cause, patch, commands/results, residual risks and receipt identities. A separate agent can review code and reproducibility; it cannot impersonate the independent human/source reviewer required by #20 or #23.

## 4. Implement the causal repairs and preserve the evaluation contract

Read the full issues rather than treating this summary as their replacement. At diagnosis commit `d5ca636a48e963619f4c89e2958d0bb1a3e72f80`, the frozen 200 pages comprised **111 complete abstracts, 7 partial and 82 absent**. The historical baseline had **91 text98 successes but 90 boundary-plus-text98 successes**. Latest primary v4 had **38 correct, zero false proposals and 73 complete abstracts withheld**, losing 55 prior successes. The olmOCR change from 40 to 39 followed changed native inputs; it does not explain those 55 persistent primary losses.

The required work includes:

- **#13:** resolve the data root before frozen imports; pin and capture the actual runtime/import closure; separate exact saved-native replay from fresh extraction. Never describe an unavailable historical environment as reproduced. Use the f154 saved-native intervention to verify the known mechanism.
- **#14:** preserve legacy scores under their original versions and add independent notation/boundary checks. `x = 1` versus `x != 1`, `x+y` versus `x-y`, and `10^5` versus `105` must not certify scientific fidelity. Keep f195's boundary defect visible until repaired.
- **#15–#17:** reconstruct logical lines with original provenance; use section ownership, layout and reading order to stop body contamination; group legitimate abstract paragraphs and internal subsections; establish evidence for closure and continuation. Exercise f039, the six alignment cases, f017/f119, f113/f186, f080, f084 and the title-page cases named in the issues. Do not hardcode sample IDs, lower alignment thresholds, waive ambiguity or count increased abstention as recovery.
- **#18:** add typed image/crop evidence with immutable source, rendering, coordinate, transcription and review lineage. Derived text offsets refer to that representation. Never invent native spans or turn OCR agreement into publication authority.
- **#21:** pass sealed, source-bound assessments through the actual field-builder API/CLI. Validate against the exact native representation; the current builder verifies a cache and then re-extracts native text. Fix that identity mismatch. Preserve candidate-only retrieval status and invalidate affected dense caches.

Use the primary research references in the issues; verify current official documentation when implementation choices depend on version-specific behavior. Research further when a concrete causal question remains unresolved, and record why the chosen solution fits the evidence. Do not substitute more research for implementing an already supported fix.

Write meaningful positive and adversarial regression tests. Preserve source identity, review/trust boundaries, immutable historical artifacts, unresolved states and honest error denominators. Update both schema copies and consumers where required. Keep first-physical-page benchmark semantics separate from complete-document ingestion.

## 5. Run the real acceptance gates

### Repository and package checks

Read current scripts and dependency definitions first. Install the required core dependencies and the supported optional PDF stack from #13; require actual PyMuPDF/Pillow coverage for PDF changes rather than accepting skipped tests. Existing commands include:

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_parallel_source*v4.py" -q
python tools/run_validation.py
python tools/validate_package.py
python -m pip install --no-deps .
trace-gc --version
```

Execute from the appropriate isolated checkout/environment. The release runner writes reports/logs and probe results; preserve historical evidence and review generated diffs deliberately. Its `PASS_WITH_EXTERNAL_GATES` status does not establish real model accuracy or completion of external gates. Hosted CI currently exercises Python 3.11/3.12/3.13 with core dependencies; confirm the live workflow and include meaningful coverage for any newly introduced optional path.

`tools/validate_package.py` validates the legacy synthetic contract; it is not the source ZIP auditor. When delivery requires refreshed release artifacts, use the current `tools/package_project.py` workflow to regenerate `MANIFEST.json`, write the ZIP to an owned external output path and audit it with `--audit`. Its default input is tracked files: include intended new source files explicitly, inspect the resulting member list and never package the private data root. Keep generated manifest/report updates consistent with the final delivered source.

Run focused checks during implementation and the required full suite/package checks on integration and the final PR head. Broaden testing to address a concrete risk or required gate. Record skips and missing dependencies explicitly.

### #19: original 200-paper regression

After #13's supported environment/root handling is in place, use a never-used output directory. Example PowerShell invocation, after resolving the actual authorized data root:

```powershell
python -m src.parallel_source_v4.extraction regression `
  --data-root "$env:TRACE_GC_TEST_DATA_ROOT" `
  --source-map validation_v3_private/parallel-v4-source-map.json `
  --output validation_v3_private/integrated200-REPLACE_WITH_UNIQUE_RUN_ID
```

Confirm the variable is nonempty and the current CLI supports the invocation. Require source/page/image checks, exact frozen replay, preservation of the actual 91 legacy-success IDs, source-correct original error cases, f195 boundaries and explicit notation results. Run/report all four cached arms; the selected configuration must meet its zero-false-proposal requirement. Correct f039 before qualifying MinerU or a fallback that uses it. Report complete recall, accepted precision, withheld/partial/absent/error denominators, changed IDs, review burden and residual failures. Exit 1 is failed acceptance; exit 2 is blocked/preflight failure, not a completed quality run.

Bind receipts to code/imports, runtime, native/converter/source/reference/metric identities and configuration. An initial #19 receipt may exclude the new image route, but including #18 later requires a new integrated receipt before freezing the final #20 configuration. Reject stale or altered promotion receipts.

### #20: independent unseen qualification

Arrange an actual attributed independent source reviewer and necessary notation expertise. Freeze the sampling frame, exposure registry, sample-size justification, numeric targets, uncertainty method, stop rules, references and exact system configuration before inspecting predictions. Include the reviewed image route in final qualification. Exclude all prior development, retrieval, diagnosis and review exposures by work/source identity.

Execute genuine selected converters and assess every preregistered criterion. Preserve unresolved cases and reviewer disagreement. Assistant-generated references are assistant review, not independent human qualification. If tuning follows inspection of this cohort, mark it exposed and obtain a new unseen cohort. A failed or unavailable qualification cannot close #20 as successful.

### #22: full retrieval experiment

Freeze and account for all **10,000 documents and 60 original queries**. Rebuild the actual fields and regenerate affected embeddings using pinned real models/tokenizers. Measure per-channel and union candidate recall before reranking; report final ranks, top-1/top-10/MRR, misses, resource use and costs. Judge competing relevant results independently of known-target rank.

Do not insert known targets, use query-dependent field repairs, silently shrink the corpus or fabricate a dense/reranker output. Track f115 and f076 explicitly. The current dense-cache query hash includes `target_id`; a label-independence test must separate ranking-input and evaluation-label identities, or rebind the unchanged rankings explicitly for that test. A cache rejection is not proof of ranking independence. Missing models or inputs remain NOT RUN.

### #23: actual paper-to-answer pilot

Before running the pilot or inspecting generated answers, freeze its real-paper cohort, independently reviewed questions and expected evidence, model/configuration, resource budget and numeric acceptance criteria. The extraction qualification freeze in #20 does not freeze this separate end-to-end evaluation. Preserve unsupported questions and conflicting evidence where the cohort supports them.

Implement and document a supported workflow for an authorized real cohort, including evidence beyond page one. Exercise source ingestion, reviewed native/image evidence, actual semantic observations, compilation/resolution, authorized publication into an isolated durable graph, retrieval and generated answers using an approved actual provider or installed model.

Use one graph authority and application-owned trust/access scopes. A durable local `SQLiteReferenceBackend` pilot is valid within the issue's scope. Reopen the database through fresh connections; verify persistence, provenance, idempotent retries, interruption/resume, source revisions/withdrawal, permission changes, rejected/stale reviews and unsupported-question abstention. Independently assess graph correctness, retrieval coverage, answer support and citation correctness. Every material answer claim must trace to exact source evidence. `CONTEXT_ONLY`, fabricated observations or a synthetic demo cannot establish this acceptance.

Production credentials, production writes, private-document transfer and paid execution require applicable authority. Use existing authorized resources and budgets; complete local implementation and other gates while arranging genuinely missing inputs. Do not represent the local pilot as qualification of distributed or production storage.

## 6. Deliver each change through a reviewed merge

For each coherent issue change:

1. Reproduce the defect and record the before-state; implement the smallest complete causal repair with the necessary tests/docs/contracts. Preserve other work and compatible behavior.
2. Obtain an independent code review of the actual diff. Resolve correctness, provenance, concurrency, privacy and test-coverage findings. If a conclusion is disputed, settle it with source evidence or a targeted experiment. Agent review does not replace required GitHub approvals or independent empirical reviewers.
3. Run the appropriate validation on the final branch head. Record the tested commit/tree and exact environment; rerun affected checks after changes. Inspect generated artifacts and the staged diff for private corpus content, credentials, accidental reports and unrelated edits.
4. Use the existing approved Git identity and verified signing configuration. Verify commits locally and confirm GitHub reports the intended signatures as verified. Repair only the scoped signing failure; never restart WSL or disable signing to get through a gate.
5. Open/update a focused PR against the current default branch. Include issue links, causal explanation, implementation summary, reproduction, tests, empirical receipt identities, limitations, migration implications and acceptance checklist. Use a body file or structured API input for multiline text.
6. Use `Refs #N` while any issue acceptance remains outstanding. Use an automatic closing keyword only when all criteria are already satisfied by evidence included in or linked from that PR. Separate mergeable implementation from still-open empirical qualification; never auto-close #19/#20/#22/#23 simply because their harness merged.
7. Reconcile the branch with current main. Resolve conflicts semantically, preserve prerequisite tests and repeat affected validation. Wait for every required check/review on the exact final head. Where protection is absent, still require the issue's relevant checks and independent code review. Fix attributable CI failures; distinguish unrelated infrastructure failures with evidence.
8. Merge using an allowed method that preserves verified commit/signature requirements. Bind the merge action to the reviewed head SHA and recheck immediately before merging. Do not use administrative bypass, delete protection, fake approval, or force-push shared/default branches. Use lease protection only on an owned PR branch when a deliberate rebase requires it, and re-fetch if the remote moved.
9. Verify the hosted merge commit, delivered diff, default-branch checks and relevant post-merge smoke/acceptance. Map pre-merge empirical receipts to the delivered source tree/import closure; if measured code/configuration changed, rerun the affected empirical gate. A different SHA alone needs an auditable identity mapping, not a fabricated rerun claim.
10. Fetch and synchronize the owned integration checkout. Fast-forward the original checkout only when safe for its existing changes; never discard them to claim a clean workspace. Update issue/epic/milestone progress and links, recording merged implementation separately from outstanding acceptance. Close the issue only after its full criteria and post-merge delivery are verified.

Keep independent ready work moving while CI or review is pending. A requested human approval that only another person can provide is a real blocker; document the exact PR/head and request, preserve the ready work, and continue everything else. Do not declare the initiative complete while that approval or any required empirical evidence is missing.

## 7. Finish with an auditable result

Before closing #12 or its milestone:

- Re-read every #13–#23 acceptance criterion and verify its completion against actual merged code and identified evidence.
- Confirm all implementation/evidence PRs are merged, final hosted checks pass, dependency links and native hierarchy remain correct, and existing #4–#11 work was preserved.
- Confirm the full configured 200-paper gate, independent unseen qualification, full retrieval trial and independently reviewed real paper-to-answer pilot all succeeded under their stated criteria.
- Preserve an immutable final manifest linking issues, PRs, merge commits, tested source identities, runtime/model/configuration versions, data/protocol/metric hashes and empirical receipts. Publish only permitted aggregate data and nonsecret identifiers; keep private papers, labels, detailed outputs and personal filesystem paths external.
- Verify safe local synchronization and account for pre-existing changes. Remove only disposable work you own when safe; retain evidence and anything needed for a pending handoff.

Deliver a concise final report with a row for each issue: disposition, merged PR/commit, acceptance evidence and any residual limitation. Include the epic/milestone links and the measured extraction, retrieval and pilot outcomes. Distinguish local reference qualification from production qualification.

Continue until all authorized work is complete. If external input makes full completion impossible, finish every independent authorized task, keep the affected issue and epic open, and report the exact blocker, completed/merged work, evidence and next action. Do not relabel blocked work as resolved or stop merely because the implementation phase is finished.

**Start now by reconciling the live issue graph, source checkout, available evidence and active ownership; then execute the first ready work.**
