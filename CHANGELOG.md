# Changelog

## [0.9.0](https://github.com/ashworks1706/louped/compare/v0.8.0...v0.9.0) (2026-10-11)


### Features

* boards, dashboards an agent writes as data: linked panels, controls, live tables, diagrams ([e1c202d](https://github.com/ashworks1706/louped/commit/e1c202d3d4c5a798a44435e8482ccc841d84237f))
* boards, figure previews and Plotly animation, Hugging Face Hub ([#78](https://github.com/ashworks1706/louped/issues/78)) ([30288fc](https://github.com/ashworks1706/louped/commit/30288fcb8c6814736a7abd7c53ca9a4e133ad048))
* Hugging Face Hub in the app and the MCP ([4d342ba](https://github.com/ashworks1706/louped/commit/4d342baba4d663af68c4a81c417c526a1fb2a1f6))
* the agent sees the figures it draws; plotly autoplay, loop and orbit ([be2f9b6](https://github.com/ashworks1706/louped/commit/be2f9b61eb714c8168e52c7bd50a989b1836d250))
* **web:** Training in the Behavior sidebar too ([#76](https://github.com/ashworks1706/louped/issues/76)) ([fbe4b93](https://github.com/ashworks1706/louped/commit/fbe4b93e5c8093637ab41f0cc880255d29af071f))

## [0.8.0](https://github.com/ashworks1706/louped/compare/v0.7.0...v0.8.0) (2026-10-07)


### Features

* pip install louped gives the full app ([#73](https://github.com/ashworks1706/louped/issues/73)) ([93d1b4f](https://github.com/ashworks1706/louped/commit/93d1b4f511bd088f192277d8f1ea32bf8b73bea2))

## [0.7.0](https://github.com/ashworks1706/louped/compare/v0.6.0...v0.7.0) (2026-10-07)


### Features

* a run's Code link opens its script at its commit; Colab as an export target ([#68](https://github.com/ashworks1706/louped/issues/68)) ([569980e](https://github.com/ashworks1706/louped/commit/569980e70e4b0ce7d59cff524c570a31a012c633))
* big results skip /tmp and large pulled artifacts stay in the remote ([#65](https://github.com/ashworks1706/louped/issues/65)) ([30c12b3](https://github.com/ashworks1706/louped/commit/30c12b341f6d1d5aba0c8333312d55a04054730a))
* catch bad training data and broken training early ([#66](https://github.com/ashworks1706/louped/issues/66)) ([8d2b1a9](https://github.com/ashworks1706/louped/commit/8d2b1a9ea093b067cc0e12a18e3939c2844c1807))
* experiment gates, and cluster jobs submitted, followed and chained over ssh ([#70](https://github.com/ashworks1706/louped/issues/70)) ([0d576f2](https://github.com/ashworks1706/louped/commit/0d576f23311e827b42b7aba0651946538b363fba))
* plugins load while the app runs; demo tour shows a column, a chart and a page the agent builds ([cfaf3a2](https://github.com/ashworks1706/louped/commit/cfaf3a289734065508ac0944edf19e4daba45619))
* plugins load while the app runs; demo tour shows a column, a chart and a page the agent builds ([4ddd1de](https://github.com/ashworks1706/louped/commit/4ddd1de0b7f30c22daa258485568acccffebe59e))
* reports grouped by experiment, and live numbers and figures in Markdown ([#67](https://github.com/ashworks1706/louped/issues/67)) ([9426fbd](https://github.com/ashworks1706/louped/commit/9426fbd8670c1a5db7cbd51fe4c3879953a525ec))
* show what the model read and which rule read each score ([#69](https://github.com/ashworks1706/louped/issues/69)) ([474fff4](https://github.com/ashworks1706/louped/commit/474fff497dd306bdd57c6fe36802dad9c6906f98))


### Bug Fixes

* cluster exports build, serve rebuilds a stale UI and restarts itself, plugins reload ([#64](https://github.com/ashworks1706/louped/issues/64)) ([1b4cb75](https://github.com/ashworks1706/louped/commit/1b4cb75d4adc6812f2546fd077bbf269a67f7b9b))

## [0.6.0](https://github.com/ashworks1706/louped/compare/v0.5.0...v0.6.0) (2026-10-06)


### Features

* picks reach the agent with the next message; [@sel](https://github.com/sel) names them ([d0d65f4](https://github.com/ashworks1706/louped/commit/d0d65f4fd05ea740e6e57e743217a6011349995a))
* picks reach the agent with the next message; [@sel](https://github.com/sel) names them ([df8e097](https://github.com/ashworks1706/louped/commit/df8e0976e4a86efeeaa1d5284ff0a067e61244a4))

## [0.5.0](https://github.com/ashworks1706/louped/compare/v0.4.0...v0.5.0) (2026-10-05)


### Features

* agent-made figures (Plotly 3D and animation) and derived columns ([ed07d18](https://github.com/ashworks1706/louped/commit/ed07d18d29e39406f5e2fccb604ab75ad16f7092))
* agent-made figures (Plotly 3D and animation) and derived columns ([d906e6d](https://github.com/ashworks1706/louped/commit/d906e6de06c062cdff8de109c2c453c33e9371b1))
* an item opens on its claim or question ([93eb9e9](https://github.com/ashworks1706/louped/commit/93eb9e97a1081ce4bdc115d046e6a2ccb409a1be))
* an item opens on its claim or question ([467f8b3](https://github.com/ashworks1706/louped/commit/467f8b357a05e5c05a3f6ea28c6d0437480a82d7))
* blind A/B of two eval runs on Compare ([686b476](https://github.com/ashworks1706/louped/commit/686b476de5a4a12803a0d2d71bbedf917a6bc5e5))
* blind A/B of two eval runs on Compare ([c76560a](https://github.com/ashworks1706/louped/commit/c76560a3ee4e969d94a8137dcd8b24d33d70b346))
* every page's parts have addresses an agent can hint ([2e06d88](https://github.com/ashworks1706/louped/commit/2e06d88034df7b0d000a5f063d8b5ab46c0523ff))
* every page's parts have addresses an agent can hint ([081cc76](https://github.com/ashworks1706/louped/commit/081cc76fa3334ee109426316b6bdbd7fd069a714))
* every part of a page is addressable: Shift+click to pick, layout rules, agent cues ([0890529](https://github.com/ashworks1706/louped/commit/089052959d03760935a3c024a84d364c47b7d5e2))
* every part of a page is addressable: Shift+click to pick, layout rules, agent cues ([a82b898](https://github.com/ashworks1706/louped/commit/a82b8984ea0da69021c91fbf1898e6d15bf0d777))
* judges as project files, and an eval task picker on Launch ([0e948f5](https://github.com/ashworks1706/louped/commit/0e948f5fcdcb3bdbf12f482d21fa0ac31f36eae8))
* judges as project files, and an eval task picker on Launch ([501e7f3](https://github.com/ashworks1706/louped/commit/501e7f3d376c63f11bc4b89766579b912fd259ac))
* keep a Probe result as a run, compare vectors and overlay curves ([1da5f0d](https://github.com/ashworks1706/louped/commit/1da5f0db672b1938f38bfa425181d3d80ef795a6))
* keep a Probe result as a run, compare vectors and overlay curves ([7b691d7](https://github.com/ashworks1706/louped/commit/7b691d78f2e3bef6ef5b49dbe97319f1bcb3ca41))
* keep the project's sources and search them ([ea49f15](https://github.com/ashworks1706/louped/commit/ea49f15c24065496b038bff540426901d006de63))
* keep the project's sources and search them ([ac601e8](https://github.com/ashworks1706/louped/commit/ac601e88b92053930fb8d0509256fde8eb69c2dd))
* louped check and the ground-claims skill ([5c615ef](https://github.com/ashworks1706/louped/commit/5c615efb9fbcdb883e6f7344c29e11a4f0b7142d))
* louped check and the ground-claims skill ([db0d7c2](https://github.com/ashworks1706/louped/commit/db0d7c29ef897099895e74a1f64af696d5c49a00))
* notebooks as papermill jobs, shown as Jupyter pages ([5566ba6](https://github.com/ashworks1706/louped/commit/5566ba6d8bb4fe09b9a99f53cc06b16daa9637e5))
* notebooks as papermill jobs, shown as Jupyter pages ([1d5345d](https://github.com/ashworks1706/louped/commit/1d5345dae6e33b22ad96bcbc0e9352280e047c21))
* picked items become a cohort: read alone with paired intervals, saved, run again ([49c0343](https://github.com/ashworks1706/louped/commit/49c03433274218c27038935a35e5ce854c71723d))
* picked items become a cohort: read alone with paired intervals, saved, run again ([156d247](https://github.com/ashworks1706/louped/commit/156d2474e64f2e332070d553bf05a7fcfa40c2ee))
* read sources in the app, pin passages and cite them ([c3193e4](https://github.com/ashworks1706/louped/commit/c3193e4c9b43fadeddea2a74debb06f6e3d23650))
* read sources in the app, pin passages and cite them ([b73e0b3](https://github.com/ashworks1706/louped/commit/b73e0b32fed7b9cfe23f01736a51aa0d10abdae8))
* reports/ with decks, documents and exported figures ([61b65b9](https://github.com/ashworks1706/louped/commit/61b65b94c5eb1a17bb89d1b1ef2d98075723ab7d))
* reports/ with decks, documents and exported figures ([f06eef2](https://github.com/ashworks1706/louped/commit/f06eef28d2cba3502f0db1a79e13fee2eb8b3e4b))
* trace a figure's point to its rows, script and commit ([02137aa](https://github.com/ashworks1706/louped/commit/02137aae9e153bb756168dfa74100461bf8847ef))
* trace a figure's point to its rows, script and commit ([e8607ef](https://github.com/ashworks1706/louped/commit/e8607efe8577afbc848c9082bdbb8fb94c9ddeea))


### Bug Fixes

* confine server-added source files before they reach add_source ([f5b51c7](https://github.com/ashworks1706/louped/commit/f5b51c701a45f9a345fd993c69bdd22166888719))
* fetch sources from public addresses only; split file and URL adds ([836fb66](https://github.com/ashworks1706/louped/commit/836fb66dd87ed59adaba24902fe4fcba8d6f235f))
* keep cohort files inside experiments/ whatever the experiment name ([1cfa302](https://github.com/ashworks1706/louped/commit/1cfa3028e10035500ff3be4945e78df9e7d9c14f))
* keep the uninstalled fallback version in step with releases ([1ccfd22](https://github.com/ashworks1706/louped/commit/1ccfd22aa138df1cf01996e8e7c5a2f6b61e2653))
* keep the uninstalled fallback version in step with releases ([eff9daf](https://github.com/ashworks1706/louped/commit/eff9daf9faeb44a8e75b15b7f23c50073e8e4f4f))
* notebook review findings ([4d921df](https://github.com/ashworks1706/louped/commit/4d921df34c3ca1c7560dc7e82337ac92948211c5))
* reports review findings ([d96f760](https://github.com/ashworks1706/louped/commit/d96f7603412d4db662d54e4e6eccfe62d0ff9f16))
* resolve blind A/B files under the state folder ([dc920ce](https://github.com/ashworks1706/louped/commit/dc920ced5768168e19be7a4b6fee8b2294b99280))

## [0.4.0](https://github.com/ashworks1706/louped/compare/v0.3.0...v0.4.0) (2026-10-05)


### Features

* agent-editable pages: layouts, presets, select mode, kit and theme ([7461c5c](https://github.com/ashworks1706/louped/commit/7461c5c060d818a97cce7ffe2831be23115f4352))
* agent-editable pages: layouts, presets, select mode, kit and theme ([85ba533](https://github.com/ashworks1706/louped/commit/85ba533a2d231dde9337d6dabc0e2f3ae8eb5bfd))

## [0.3.0](https://github.com/ashworks1706/louped/compare/v0.2.0...v0.3.0) (2026-10-05)


### Features

* plugin tabs on runs and experiments, edit any run text file, delete to the trash ([#34](https://github.com/ashworks1706/louped/issues/34)) ([076d9dc](https://github.com/ashworks1706/louped/commit/076d9dc9aa07c35e280a47fde80cd56b7eb187bb))

## [0.2.0](https://github.com/ashworks1706/louped/compare/v0.1.3...v0.2.0) (2026-10-05)


### Features

* edit an experiment's README and a run's Markdown in the app, beside its rendering ([75e5e1a](https://github.com/ashworks1706/louped/commit/75e5e1ab35894d54dc712b4c5a22413584ca23b1))
* project plugins add pages, routes, commands and agent tools without a louped release ([694844d](https://github.com/ashworks1706/louped/commit/694844dce9871074f4389d5a548ee139898bfe0b))
* push and pull set up a remote and ask for a Hugging Face token when one is needed ([cea26f9](https://github.com/ashworks1706/louped/commit/cea26f9a5b317fff2f2240d961194fcf3f6de46f))
* share runs through a remote, edit Markdown in the app, and project plugins ([c321a50](https://github.com/ashworks1706/louped/commit/c321a50e54655f81ed373363e6b4e3777fa4779c))
* share runs through a remote, one-file cluster jobs, vega figures and a published dashboard ([0e7656a](https://github.com/ashworks1706/louped/commit/0e7656a1e3d6c946799fad468ee160b29ca34803))


### Bug Fixes

* guard a saved run Markdown path the way code scanning recognizes ([5490c4f](https://github.com/ashworks1706/louped/commit/5490c4f29efece42dbfe1348e8ad60255ac6a407))
* one path check when a run's Markdown is saved ([aa0334e](https://github.com/ashworks1706/louped/commit/aa0334e1b222647b24689b6c7535a448c9fc4312))

## [0.1.3](https://github.com/ashworks1706/louped/compare/v0.1.2...v0.1.3) (2026-10-04)


### Bug Fixes

* PyPI and the README point to the website, louped.vercel.app ([0209563](https://github.com/ashworks1706/louped/commit/0209563de6e40f10d101f2cbb4474189f5e0b7b0))

## [0.1.2](https://github.com/ashworks1706/louped/compare/v0.1.1...v0.1.2) (2026-10-04)


### Bug Fixes

* the image copies hatch_build.py, which building louped needs ([dc7c67f](https://github.com/ashworks1706/louped/commit/dc7c67f765813bee28255ac680d67b61ab0fe1c4))

## [0.1.1](https://github.com/ashworks1706/louped/compare/v0.1.0...v0.1.1) (2026-10-04)


### Bug Fixes

* uv.lock at 0.1.0, and release-please bumps it with the version ([d58f954](https://github.com/ashworks1706/louped/commit/d58f954c88fdaeaeb8088beaa522b5b30951e585))

## 0.1.0 (2026-10-04)


### ⚠ BREAKING CHANGES

* the import, the command, the project file and the state folder are renamed. A project made with loupe renames loupe.toml to louped.toml and moves .loupe/ to .louped/, rewriting MLflow's artifact paths and loupe.* tag keys.

### Features

* benchmarks experiment, any inspect_evals benchmark on any model or endpoint ([c4deaca](https://github.com/ashworks1706/louped/commit/c4deacadbd0e2f5530d09edd94eaf87d5dd900d2))
* distillation data and a small classifier recipe ([4bdaf0f](https://github.com/ashworks1706/louped/commit/4bdaf0f06af8bc368b4c849f72d322d8dc48c1c0))
* DPO and GRPO recipes, one check as reward and scorer, training dynamics ([11f9c81](https://github.com/ashworks1706/louped/commit/11f9c8166757c50fe2f79c026c2120dd86b7996b))
* embed Inspect View, circuit-tracer's viewer and Neuronpedia ([d320ddf](https://github.com/ashworks1706/louped/commit/d320ddf0c1a7a7d973f1ff03571e25212623173a))
* endpoint-bench, line up one file by a column, declared extras, recipes ([78a81dd](https://github.com/ashworks1706/louped/commit/78a81ddd8ab733a3831ccf85be2c024630976e53))
* evaluate opaque agents, regression cases, replayed tools, tau-bench ([b7dc79d](https://github.com/ashworks1706/louped/commit/b7dc79d7aafadd06f4cf86d871928323e8e89ff4))
* evaluate opaque agents, regression cases, replayed tools, tau-bench ([ba76edf](https://github.com/ashworks1706/louped/commit/ba76edf7565038c941b24a910f2123e5545ae3eb))
* experiment pages, research board, toasts and job notices ([f22d86c](https://github.com/ashworks1706/louped/commit/f22d86c28d1bb7541b32f27f218b316db8ae566f))
* explain every figure behind a ?, and fill empty pages from the app ([134f7e8](https://github.com/ashworks1706/louped/commit/134f7e8e384b2a24c70c4cb8f2a77b1ab7db3303))
* explain every figure behind a ?, and fill empty pages from the app ([71bc4d3](https://github.com/ashworks1706/louped/commit/71bc4d30dc9af6fefae3dc5d484af7db57df7f0e))
* grid, adapter bank and soft prompts as research domains ([8553619](https://github.com/ashworks1706/louped/commit/8553619c18a17acd347e5d73af5f89395964c4d4))
* interp-toolkit experiment; docs for the interp toolkit ([c543d39](https://github.com/ashworks1706/louped/commit/c543d395b78395fdc0800b606a56e1f740282e1c))
* judge two eval runs pairwise with a local model, checked against your labels ([#17](https://github.com/ashworks1706/louped/issues/17)) ([0dac8d9](https://github.com/ashworks1706/louped/commit/0dac8d91bc787616e8e473b3dec59e812388c39a))
* launch and configure from the UI, verified on real models, domain-focused ([4b22ab3](https://github.com/ashworks1706/louped/commit/4b22ab3fd7f0f70b6ec3fd3d20036d6943db9ee7))
* launch and configure from the UI, verified on real models, domain-focused ([614661d](https://github.com/ashworks1706/louped/commit/614661d1660169a602495f83a0793d3a792eb4ff))
* linear probes, attention patterns and attribution patching in loupe.analysis ([289717e](https://github.com/ashworks1706/louped/commit/289717e8f8690b9bae5dcba35048fef7d40a7301))
* loupe mcp, an MCP server for coding agents ([e81cb66](https://github.com/ashworks1706/louped/commit/e81cb665648c768873260c0bea37b28875fa0a53))
* loupe mcp, an MCP server for coding agents ([d14e9e0](https://github.com/ashworks1706/louped/commit/d14e9e0adff1994d087710de94d70ba3c1683b3b))
* phase 1 skeleton for loupe ([60495ee](https://github.com/ashworks1706/louped/commit/60495eec71f69e1ece5e8656a1db9ad29d30d0ce))
* phase-routed adapters and a masked diffusion backend ([ac5cfe9](https://github.com/ashworks1706/louped/commit/ac5cfe900c9b63aa51986bc4e2d1671ae4d02f18))
* pip install to a first result: loupe init, loupe view, and the agent harness ([5013238](https://github.com/ashworks1706/louped/commit/5013238596fdfb7c87761fb0a1c67766d22ed907))
* rational-updating baseline through the authors' harness ([558377d](https://github.com/ashworks1706/louped/commit/558377d831ecf20f4b60d672130705aec9bcbcfc))
* rational-updating baseline through the authors' harness ([402816f](https://github.com/ashworks1706/louped/commit/402816f1c071cfb01e7c678c5284e604a4464ba5))
* refocus on interventions; multi-turn GRPO environments and verifiable tasks ([8c67290](https://github.com/ashworks1706/louped/commit/8c67290a4eb4271877cc186938e2c8f33e46d722))
* research tools in the Playground and cost views for efficiency ([5aea49f](https://github.com/ashworks1706/louped/commit/5aea49f15e89cc2fb0f9550b23cc01814b5dd55d))
* research tools in the Playground and cost views for efficiency ([7e77797](https://github.com/ashworks1706/louped/commit/7e777974d1eb6ea3fcd51a6614475b8d288d995c))
* research-grade interp, evals, training and agents ([a34824c](https://github.com/ashworks1706/louped/commit/a34824c77c77c9a224309610c65ce6ce066b2e63))
* retrieval and retrieval inside the model as domains ([f80a5fc](https://github.com/ashworks1706/louped/commit/f80a5fce83b6bd2bf255438b3e4ddb6007041f0f))
* run a launch on Sol, a Slurm cluster or a VM, and import its result ([#19](https://github.com/ashworks1706/louped/issues/19)) ([ff40436](https://github.com/ashworks1706/louped/commit/ff404360c015e6b423ddf452f4e0d155a474e4a7))
* run grids and new experiments from the app; drop CLI flags the app covers ([3d98680](https://github.com/ashworks1706/louped/commit/3d986800af10b19887f9d3843e090a52ccb08f3f))
* run grids and new experiments from the app; drop CLI flags the app covers ([04ef961](https://github.com/ashworks1706/louped/commit/04ef96192d18375bdcceaa6452c69e3a407d220c))
* run Neuronpedia locally with just neuronpedia ([6cfd913](https://github.com/ashworks1706/louped/commit/6cfd913d07481e0616792df1f3b542766310fdb1))
* SAE features link to their Neuronpedia dashboards ([74e0965](https://github.com/ashworks1706/louped/commit/74e096517860b0ef6d968c9315c7baa922d2315c))
* SAE features through SAELens in a new sae extra ([a463eef](https://github.com/ashworks1706/louped/commit/a463eef308a0da9c3a14cc93b8711d575ec47bf0))
* serving cost bench, quantized weights, speculative decoding and profiling ([#18](https://github.com/ashworks1706/louped/issues/18)) ([350295e](https://github.com/ashworks1706/louped/commit/350295e1daf0ecf30a05a46a38c24647e53fb6da))
* sycophancy pushback experiment as the mechanisms domain ([810ed5f](https://github.com/ashworks1706/louped/commit/810ed5ffd1e396f3f06f95bf2493e3adb0c90d3d))
* the machine on every run, models with their own code, and inject at an engine's hook points ([aac4d91](https://github.com/ashworks1706/louped/commit/aac4d914eb0fa09c4443a2cc3cf25f8cced78548))
* time to first token and nanoDiff checkpoints ([d0f1f39](https://github.com/ashworks1706/louped/commit/d0f1f3966963614f7be148497dd344dda33eb41d))
* token views, live Inspect, paired comparison and steering sweeps ([29e5ef0](https://github.com/ashworks1706/louped/commit/29e5ef01b9151f2863199f3e5e9e362504713780))
* tool agents through the loupe provider, tool-call transcripts, sandbox task ([0341c8c](https://github.com/ashworks1706/louped/commit/0341c8cc5629f4f256daca809a53dc4eb7d44cf0))
* training sets and LoRA SFT migrated from zipy and SparkyAI ([a06063a](https://github.com/ashworks1706/louped/commit/a06063ac8c126d3a5c9dfe41bc1b7927cd1ff46a))
* v0.2 UI on real Inspect and MLflow runs ([767a838](https://github.com/ashworks1706/louped/commit/767a83855614c4e3ce6bed81c9a6140b74650b79))
* v0.3 interp core, refusal-direction pipeline, Figures tab and Vectors page ([6bfffe6](https://github.com/ashworks1706/louped/commit/6bfffe6217fc0123cfcc441ae612c4be82a79295))
* v0.4 Inspect model provider and Playground ([b8052ed](https://github.com/ashworks1706/louped/commit/b8052ed975d4413508538aff6d2ad8847e609068))
* **web:** a run's items across conditions, its files by type, and its provenance ([5c11188](https://github.com/ashworks1706/louped/commit/5c111881caf2db892cca3eb9e2570984086f2557))
* **web:** agent traces as timelines; a large folder's files filter, scroll and read as one ([c493e1e](https://github.com/ashworks1706/louped/commit/c493e1e377caea32ca0b658a0154e108f24b3408))
* **web:** domain routes, job page with progress, top bar and foldable sidebar, examples ([7471dcd](https://github.com/ashworks1706/louped/commit/7471dcdc34e24cb521c41efd5d19c553010aac40))
* **web:** domain routes, job page with progress, top bar and foldable sidebar, examples ([5f7ecf4](https://github.com/ashworks1706/louped/commit/5f7ecf4db1608bfc456ec100ec40708a8e981bbf))
* **web:** organise the app by research domain, with help on every term ([be7f6e8](https://github.com/ashworks1706/louped/commit/be7f6e8b23b0d6ce0a1bab40a840bd789d0f4da0))


### Bug Fixes

* address review findings on the research domains ([447ad6f](https://github.com/ashworks1706/louped/commit/447ad6f22f479151caa66cbe428ba43fb6bf7baa))
* address review of the research tools ([1d8f8a4](https://github.com/ashworks1706/louped/commit/1d8f8a4e177e234dc8ea13439627b5aa38a6eefb))
* close the Neuronpedia sheet by its button in e2e; no db password ([c28de2f](https://github.com/ashworks1706/louped/commit/c28de2f181c3bd3cbda779db94971a8b55fd1046))
* harden the rational-updating baseline after review ([a9ec360](https://github.com/ashworks1706/louped/commit/a9ec36079a43b977e66c5f7ba3f81e92b20e1d98))
* keep a harness venv out of exported results; save per-item records ([6e5037e](https://github.com/ashworks1706/louped/commit/6e5037e799daa27b544862b662909f157164ddeb))
* keep a harness venv out of exported results; save per-item records ([573fe30](https://github.com/ashworks1706/louped/commit/573fe3043ee5dc368aaea7e0e4af8ac8c1c126ec))
* review findings on the embedded viewers ([2a9cf92](https://github.com/ashworks1706/louped/commit/2a9cf920cfe6a034af21f9f7af67b7f02ddc37b2))
* review findings on training, sweeps, compare and tool agents ([16d8773](https://github.com/ashworks1706/louped/commit/16d877323edcce3409d7a2b3d8f4ca578dd8a7f8))
* Sol exports use the public partition and a longer download timeout ([1175c60](https://github.com/ashworks1706/louped/commit/1175c60ad606fcc0c7cb7f3246197c234b3cdb80))


### Documentation

* a landing page that shows how loupe is used; release-ready packaging ([5b95585](https://github.com/ashworks1706/louped/commit/5b95585df51ce8e0023719c1748e398bcd12c60f))
* add a masked diffusion backend to the project tracks ([a4e3599](https://github.com/ashworks1706/louped/commit/a4e3599bbc38518203d727021f5e5607e8447f9e))
* architecture layer diagram matches the import contract ([d86746c](https://github.com/ashworks1706/louped/commit/d86746cdfeab2fb5194d028aea858e8c68397531))
* experiments belong to projects, not to louped's docs ([59f9225](https://github.com/ashworks1706/louped/commit/59f9225e78997421da58387a0b30a10d2ce2a4f0))
* frame loupe as a testbed for LLM behavior and efficiency research ([71cc1ef](https://github.com/ashworks1706/louped/commit/71cc1ef4b4d6647b2c2a4b800b4daab1788cc06b))
* organise the roadmap and architecture by research domain ([bfa9905](https://github.com/ashworks1706/louped/commit/bfa9905c0f683562da053df622d5bb0b20c1401f))
* raise the Python line budget to ~6k ([95ba373](https://github.com/ashworks1706/louped/commit/95ba373c38991a9d7225674e71760fe6c96ee945))
* roadmap tracks for zipy, SparkyAI, piramid and Bijou research ([4dc70d6](https://github.com/ashworks1706/louped/commit/4dc70d6a9a67615728e2fe29773b314461898a0a))
* separate the diffusion backend from the other-tools list ([6f5eee4](https://github.com/ashworks1706/louped/commit/6f5eee466191922676684c7473d955b456795d8c))


### Miscellaneous Chores

* rename loupe to louped ([a02765b](https://github.com/ashworks1706/louped/commit/a02765b95d045bde97458e50efca626a0a7d9b19))
