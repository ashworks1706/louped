# Changelog

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
