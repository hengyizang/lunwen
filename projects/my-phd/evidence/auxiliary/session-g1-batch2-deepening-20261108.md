# Evidence deepening for batch 2 candidates 1 and 3

**Provenance:** current Codex session draft, exact API model identity unavailable, no native runtime receipt, no topic approval.

Prepared 2026-11-08. This is a source-based revision of two *candidate questions*, not an independent scientific review or a G1/G2 decision. The supplied formal project remains `my-phd`, G1 `awaiting_work`, with G0 approved. The earlier proposals remain historical records. Their broad contact-history and thermal-history motivations now have direct prior art and must not be presented as established gaps.

## 中文概览

已实际下载并阅读两方向各5篇近邻的科学主文；另读主动辨识、接触不确定性校准、热模型验证、逆热规划及实验质量控制的相邻研究。1篇装配论文通过全页OCR阅读，并目视核对关键页；公式推导和数表没有独立复核。其余正文为PDF文本阅读，不能等同复现实验或完整审计所有补充材料。

- **机器人装配：原宽问题需改。** 从接触历史学习、柔顺控制、混合力位控制和主动探测都已有强先例。可继续查证的是：当摩擦、间隙和传感偏置产生难以区分的观测时，学习方法能否知道何时证据不足，并在相同信息和算力下优于调好的辨识/MPC及信息增益探测。这个窄问题也可能没有新意。
- **增材制造：原宽问题已有直接先例。** 恒定线能量下的热累积、时空残余热因子及跨路径热预测都已有研究。可继续查证的是：在独立试件/扫描策略外推、计入测量误差后，学习残差是否仍比热传导和热源标定多解释真实熔池宽度/面积。
- **入口还未证明可运行。** robosuite版本和源码已定位，但默认对象真值会泄漏，实际CPU耗时未知。NIST有版本、文件大小和提供方校验值；README两次请求HTTP 500，原始XLS/ZIP未下载，独立试件对应关系尚未核清。

保留1和3作为优先查证的一对候选，不替用户选题，不给七权重评分，不承诺六篇独立论文、Q1发表或新截止日期。下一步只应在真实G1选择及实验协议成立后开展实验。

## Scope and evidence standard

The owner now explicitly prefers AI interacting with mechanics, robotics, manufacturing, mechatronics or autonomy. Reported mechanical-engineering and data-analysis experience supports examining these intersections; control, finite-element and laboratory proficiency remain unverified. The seven original weights remain 25% funded-position supply, 25% jobs/salary, 15% growth, 7.5% PhD competition, 7.5% job competition, 10% background fit and 10% application fit. No new career, salary, funding or eligibility evidence was collected; missing factors were not renormalized away.

The companion `batch2-deepening-source-notes.json` freezes exact requested URLs, observed versions, raw-byte SHA-256 values, retrieval outcomes and reading coverage. IDs below refer to that ledger. Ten core papers have their scientific main bodies read: five for each direction. Five additional primary papers cover adjacent domains. A downloaded TRANSIC paper was only identified, not scientifically read; it is excluded from these counts. References are not treated as papers read. Mathematical arguments were read where extractable but not independently proved. Figures were generally read through captions; corrupted plot glyphs and unread supplements are explicitly excluded. This is bounded evidence, not a systematic or exhaustive novelty search.

Public PDFs, metadata and source code were read without credentials. No robot, simulation, training, dependency installation or scientific experiment was run. No raw experimental dataset was downloaded. Temporary source bytes remain under `/tmp/lunwen-batch2-deepening/`; this draft does not claim a durable raw-document archive. The new persisted artifacts contain paraphrases and source fingerprints, not copies of articles.

## Candidate 1: observability limits and useful probing in contact assembly

**Original broad question:** learn from force/motion history when to change compliance or search direction. **Disposition:** occupied at the level stated. Recurrent contact policies, residual admittance, geometric constraint reduction and active information gathering already address its main components.

### Nearest primary papers actually read

| ID and source | Shared mechanism, established result and boundary | Consequence for this candidate |
|---|---|---|
| C1 — [Focus-Then-Contact](https://proceedings.mlr.press/v306/qiao26f.html), 2026; main §§3–4 and scientific appendices | Demonstration-pretrained ACT plus residual SAC, affordance reward and timed human intervention use visual/force feedback. The no-intervention ablation fails in the reported setting. Training includes a real arm and an RTX 4090 reward classifier (§4.3); visually difficult and long-horizon cases remain limited. | Residual learning and contact-focused training are prior art. “Lightweight” and minutes on author hardware do not establish CPU-only reproducibility. Human demonstrations/interventions must be counted as resources. |
| C2 — [VT-Refine](https://proceedings.mlr.press/v305/huang25b.html), 2025; main §§3–6 and appendices A–D | Visuo-tactile diffusion pretraining is refined in GPU-parallel tactile simulation and transferred to real bimanual assembly. Normal-force tactile feedback already enables corrective motion. Manual alignment, tactile fidelity, shear/deformability and hardware dependence limit scope. | Do not propose tactile history plus RL as a gap. Its high-dimensional GPU/hardware pipeline is an adjacent capability comparison, not a runnable CPU baseline. |
| C3 — [Force Policy](https://www.roboticsproceedings.org/rss22/p128.html), 2026; §§IV–V, especially IV-A and V-A | Global visual decisions and local GRU pose/wrench histories learn interaction frames, selection masks and hybrid force-position actions. The paper explicitly identifies stiffness/friction ambiguity in local signals and adds a visual semantic prior. Assumptions include compensated dynamics and locally stable contact structure. Evaluation uses real hardware and GPUs. | The proposed history-to-mode/compliance inference is directly crowded. A different recurrent architecture is insufficient. Reading its external semantic-model component does not imply this session called that model. |
| C4 — [Efficient Sim-to-real Transfer … with Online Admittance Residual Learning](https://proceedings.mlr.press/v229/zhang23e.html), 2023; §§3–5 and scientific appendices | MuJoCo SAC predicts motion/stiffness; online SQP updates residual admittance using recent force replay. Retuned manual gains are strong in the original setting. Diagonal parameters, imperfect replay extrapolation and initial unsafe contacts limit the method. | A properly tuned optimization/controller rival is mandatory. Replacing its predictor with a neural estimator does not establish a new contribution. |
| C5 — [Robust Peg-in-Hole Assembly under Uncertainties via Compliant and Interactive Contact-Rich Manipulation](https://www.roboticsproceedings.org/rss21/p060.html), 2025; scientific main body and appendix A–D, OCR with visual checks of PDF pp.5,10,13,16 | Contact interactions reduce hole-pose uncertainty and create execution funnels; MPC uses online linear/RLS updates. Known geometry, stable grasp, tactile pose estimation and largely planar/quasi-static structure matter. Appendix D reports about 30 Hz for the authors’ MPC, with no current-runner measurement. | Contact-based uncertainty reduction already has a strong physical alternative. OCR mathematics and quantitative tables were not audited; the qualitative method and discussion are usable evidence. |

### Three adjacent domains and their implications

1. **Classical compliant control and online system identification:** C4 and C5 already combine mechanics with adaptive optimization. Compare learning with equal observation histories, tuning access and action constraints, not a fixed-gain straw baseline.
2. **Active experimental design:** A1, [Behavior Synthesis via Contact-Aware Fisher Information Maximization](https://arxiv.org/abs/2505.12214v2), main scientific body and appendices, explicitly optimizes contact-rich excitation for parameter estimation. Its deterministic dynamics, Gaussian observation model and chosen contact model leave model error and joint identifiability as limitations. Information gain alone is therefore not a new assembly contribution.
3. **Contact-dependent uncertainty calibration:** A2, [Particle-Based Conformal Prediction … in Stratified Configuration Spaces](https://proceedings.mlr.press/v329/marques26a.html), main §§1–7, already provides contact-stratum-dependent one-step regions and planning tests. Assumptions 1–2 and §6.3 require exchangeable transitions and known constraints/stratum indexing; §5.2 expressly excludes multistep coverage. Unknown geometry/bias and closed-loop shift cannot inherit its guarantee by assertion. Appendices were not read.

### A narrower, still unvalidated question

**Working pilot title:** *When Contact Histories Are Insufficient: Probe or Abstain Before Changing Assembly Compliance.*

For a pregrasped rigid peg and known nominal fixture, can a small learned belief/decision model use measured pose, velocity and wrist wrench to choose a bounded probe or continue insertion, while matching or improving the force–completion tradeoff of calibrated online identification and contact-aware information planning under held-out nuisance combinations? Friction, clearance, force bias and contact-law error must be varied separately before being combined. The estimator should represent task-relevant uncertainty, rather than claim that every physical parameter is uniquely identifiable.

This is a candidate test, not a novelty claim. C3 already recognizes ambiguous local signals; A1 already chooses informative contact actions; A2 already calibrates contact-dependent uncertainty. An exact input/assumption/guarantee comparison is required before claiming that their combination leaves an unmet question. If these prior methods already cover the proposed observation limits and decisions, revise or stop the candidate before training.

**Strongest competing explanation:** a tuned geometric search plus residual admittance/RLS and a suitable probe accounts for the entire benefit. Other rivals are privileged simulator state, a contact-model artifact, greater tuning effort, a different action budget or more informative training coverage. A learned hidden state is not evidence of a correctly identified physical contact mode.

**Small falsification protocol, proposed only:**

1. Freeze a low-dimensional, pregrasped task and an observation allowlist. Use true parameters/contact labels only for evaluation or an explicitly labeled oracle ceiling. Construct nuisance pairs that initially produce similar permitted observations but different subsequent responses. If no such ambiguity survives realistic measurement precision, the motivating mechanism fails.
2. Give a tuned compliance/search controller, force-replay optimizer, contact-aware information probe and small learned history model the same histories, tuning split and bounded action/force budget. Include state-only, matched fixed probe and shuffled-history controls. A model-specific ablation cannot replace these rivals.
3. Hold out complete geometry/nuisance families and training seeds. Compare completion, jams, force exceedances, useful uncertainty and total simulator/optimization/training time. Declare success margins only after measurement and task tolerances are known, before inspecting held-out outcomes. No safety guarantee is assumed.
4. Falsify the learning claim if it loses to the tuned physical rival, gains only from oracle states or extra excitation, disappears under a defensible alternate contact law, or cannot detect insufficient information. A negative result belongs in the independent archive; it does not automatically justify a new paper.

**Independent units and leakage:** one time step is not a replicate. Distinguish training seeds, condition families and rollouts nested within conditions. Evaluation across random starts of one nominal fixture does not establish new-geometry transfer. Do not use future wrench samples, object/fixture ground truth, contact labels, hidden friction or simulator solver state in deployable inputs. Reusing model-specific tuning or calibration cases in the test set invalidates the comparison.

### robosuite entry and resource stop line

I1–I6 freeze official release metadata and static files. The observed latest release is **v1.5.2**, published 2025-12-24, resolving to commit **824ac14cefcfb7ec125fe5eb2e0bad7364466154**. This is an observed version, not a claim that future `latest` stays fixed. `setup.py` requires `mujoco>=3.3.0` and other ranges; the release alone is not a complete dependency lock.

`NutAssembly` provides a real source entry. Its constructor defaults to camera observations and an offscreen renderer; both would need explicitly disabling for a nonvisual headless probe. Object observations default on and directly return nut poses. Source `robot.py` exposes simulated `ee_force`/`ee_torque` through gripper sensors; their sign, frame, compensation, availability on a chosen gripper and correspondence to a physical sensor were not executed or validated. The task includes grasp/release and a coarse on-peg success test, so it is not already a validated precision-insertion benchmark. Pregrasp initialization, geometry tolerances and jamming metrics require a reviewed protocol.

No actual GitHub-runner CPU, RAM, episode time, training time or quota measurements exist. Static low-dimensional/headless entry points are evidence of a possible route, not measured CPU feasibility. Do not adopt the GPU training budgets of C1–C3. Stop before scientific claims if the permitted observation/action interface or meaningful contact conditions cannot be implemented without hidden state; pause the experimental plan if an initial real-runner build and timing probe exceeds its observed free capacity. No paid GPU or laboratory access is assumed or newly authorized.

## Candidate 3: transferable thermal residuals beyond calibrated physics

**Original broad question:** learn thermal memory beyond line/volumetric energy density. **Disposition:** already established as a physical effect and addressed by direct models. The candidate needs an experimentally identifiable, predictive increment beyond strong physics and calibration rivals.

### Nearest primary papers actually read

| ID and source | Shared mechanism, established result and boundary | Consequence for this candidate |
|---|---|---|
| M1 — [The trace of heat](https://doi.org/10.1007/s40964-025-01147-9), 2025; §§2–4 and data availability | Transient nonlinear diffusion calibrated on a single track reproduces history-dependent width/area for converging/diverging IN625 bare-plate scans at constant line energy. Physical repeat/operator measurements and contamination exclusions matter. A modified pause is illustrated computationally. | “History matters despite equal energy density” is not a new finding. A learned residual must beat this calibrated thermal baseline on independent physical outcomes. |
| M2 — [Physics guided heat source … IN718](https://doi.org/10.1038/s41524-024-01198-6), 2024; main Results, Discussion and Methods, including Eq.19 | Thermal-fluid simulations compare heat-source calibration schemes against AM Bench outputs. A spatial–temporal Residual Heat Factor is already explicit. Agreement on melt-pool dimensions does not ensure cooling-rate or transient agreement. | Adding a history factor or fitting geometry alone is insufficient. This CFD model is not a cheap conduction baseline; its different fidelity/cost must remain visible. Separate supplementary files were not obtained. |
| M3 — [Physics-Informed Surrogates for Temperature Prediction of Multi-Tracks …](https://arxiv.org/abs/2502.01820v1), 2025 v1; §§1–4 and figure captions | Sequential PINNs carry the previous thermal state; an enriched DeepONet models scan paths against finite-difference solutions. All six permutations of three tracks are used in training. Training uses an A100; experimental validation and broad unseen-path transfer are absent. | Learned thermal memory and operator surrogates are prior art. Accuracy on those paths does not establish physical transfer or cloud-CPU training feasibility. Some plot glyphs in extraction are unreadable. |
| M4 — [Enabling geometry and toolpath generalization …](https://doi.org/10.1038/s44387-026-00088-0), 2026; main methods/results and Table 1 | A U-Net with signed-distance/time features predicts maximum-temperature maps across synthetic FE geometries. Restricted physics, raster structure and parameter ranges remain. GPU forward time excludes substantial feature generation; experiments are not the validation target. | Cross-geometry/path learning is already occupied. Maximum-temperature maps are not complete transient histories, and synthetic FE truth is not experimental truth. |
| M5 — [Toward real-time feedback control …](https://doi.org/10.1016/j.addma.2025.105041), 2025; §§2–4 and data statement | An AMMT/FPGA-camera PID loop adjusts power from approximate melt-pool area on bare plates. The reported 118 µs is sensing-to-actuation reaction time, not cloud inference or physical settling time. Data are available on request, not established as public downloads. | PID and direct feedback are real rivals. No available local hardware or public control dataset supports promising a closed-loop manufacturing demonstration. |

M5 corrects a historical metadata conflict: the NIST webpage called it *Additive Manufacturing Letters* and listed 2025-09-25; the downloaded final PDF is *Additive Manufacturing* **114 (2025) 105041**, online 2025-11-29. Preserve both records and use the identified PDF version for scientific claims. No old artifact was silently corrected.

### Three adjacent domains and their implications

1. **Thermal metrology and model validation:** A3, [Quantifying Thermal Model Accuracy …](https://doi.org/10.1007/s40192-025-00430-5), scientific main body, conclusion, similarity-measure appendix and data statement, compares a conduction model to AM Bench Pad Y thermography. Registration, smoothing and scale alter scores; correlation misses magnitude errors. Local cooling-rate agreement is weak even when coarser patterns improve. A learned residual can otherwise learn measurement/registration error. Its thermographic benchmark is distinct from M1’s width/area dataset.
2. **Inverse physical process planning:** A4, [The inverse heat placement problem …](https://doi.org/10.1016/j.jmatprotec.2024.118447), main §§1–5, already jointly optimizes path, speed and power using constrained heat placement, with preliminary AMMT evidence. Fixed path topology and special scanner/controller access limit generalization. A thermal surrogate plus optimization is not automatically new; a simulated benefit is not an observed physical improvement. Separate experimental supplements were not read.
3. **Experimental quality and adaptive sampling:** A5, [Active oversight and quality control in standard Bayesian optimization …](https://doi.org/10.1038/s41524-024-01485-2), full main body/Methods, uses a second GP to constrain sampling using raw-data quality. Its PLD evaluation samples a surrogate of earlier experimental data, not new LPBF closed-loop trials. Filtering may remove scientifically meaningful regimes. A quality-aware GP or acquisition function is therefore a baseline, not an originality claim. Its optional human scoring is a paper method, not a new project approval requirement.

### A narrower, still unvalidated question

**Working pilot title:** *Does a Learned Thermal Residual Transfer Beyond Calibrated Diffusion and Measurement Uncertainty?*

For timestamped laser power/position and scan geometry, can a deliberately small, physics-referenced residual model predict *measured top-surface melt width/area* for held-out physical scan families better than recalibrated conduction, a residual-heat/cooling kernel and a matched-capacity statistical model? The claimed increment must remain after separating operator error, specimen/batch differences and measurement alignment. No pore, strength, melt-depth, multilayer-part or cooling-rate claim follows from width/area labels alone.

**Strongest competing explanation:** apparent memory is already explained by calibrated transient diffusion or a simple spatial–temporal cooling kernel. Apparent residual transfer is due to operator/batch effects, absorptivity calibration, a registration convention or leakage between related tracks. The same-data physics-model target can also make a surrogate look accurate while merely reproducing its generator’s errors.

**Small falsification protocol, proposed only:**

1. Acquire and verify the small public manifest/data files before any fit. Resolve specimen, scan, track, geometry, experimental-set and operator IDs. Register what qualifies as a physically independent holdout. If identities or commanded histories cannot be matched, stop this experimental claim; do not substitute a random row split.
2. Reproduce the task definition and measurement uncertainty, then freeze calibration/training/validation/test groups. A single-track absorptivity calibration, diffusion baseline and simple residual-heat rival come before a flexible learner. Fit all methods only on permitted calibration groups and disclose supplied physical priors.
3. Evaluate leave-family and, only if genuinely supported, leave-set/specimen-out predictions. Compare physical-unit error, bias by region/history regime, uncertainty adequacy and end-to-end resource cost. Use operator repeats to estimate measurement uncertainty, not to multiply the physical sample count. Reversing/shuffling history while preserving nuisance groups is a negative control, not independent data.
4. Reject the incremental-learning claim if its advantage is within defensible measurement/repeat uncertainty, disappears after matched calibration or group holdout, or survives only on simulation-generated truth. Define the practical and statistical margins before held-out outcomes, once data precision and independent-unit counts are known. A failed hypothesis is archived, without a promise of publishability.

**A useful result could be a limitation:** the permitted observations may not distinguish incorrect source absorption from missing hydrodynamics or measurement bias. A negative transfer/identifiability result would narrow what the data support. It is not evidence that the intended AI method is novel or that six manuscripts follow.

### NIST/code entry, independent units and resource stop line

I7 is the actual NIST record for DOI **10.18434/mds2-3662**, observed version **1.0.1**, titled *Dataset for Model Validation of Transient Melt Pool Dynamics in Laser Powder Bed Fusion of Nickel Superalloy 625: Top Surface Width and Area Measurements for Rapidly Converging and Diverging Hatch Strategies*. Metadata lists `Measurements.xlsx` (376,701 bytes), `Scan Strategy Data.zip` (28,583 bytes), `Image Data.zip` (495,271,476 bytes) and `README.txt` (8,473 bytes), with provider SHA-256 checksums in the JSON ledger. These are advertised file sizes/checksums, not independently verified raw downloads.

The public metadata endpoint succeeded. Both official README routes returned HTTP 500. XLS/ZIP payloads were not downloaded, so availability, schema and all file-to-specimen relationships remain unresolved. Version-history dates distinguish a 1.0.0 release and a 2026-01-06 1.0.1 collection update; a metadata modification date is not automatically the date of each experiment.

M1 describes two experimental sets; three fabrication repetitions and two operator readings in the repeated set do not give six independent specimens. Tracks are nested in a scan, scans may share a plate/batch, and geometry is shared across repeats. It also states “32” geometries alongside “18 converging and 18 diverging”; this arithmetic discrepancy is unresolved. Do not infer an independent sample count from these prose totals. Dataset IDs must decide the grouping before a power or transfer claim.

I8–I11 locate the authors’ public GitLab simulation project and exact README/CMake blobs. The observed tree pins an `mlhp` submodule at **a657112d6ee4771505b4987224cac7a2e2c309b8**. CMake builds C++ examples with 4D library instantiations and Python bindings off; the mostly templated README is not a complete portable build recipe. Dependencies and a working reproducible build remain unverified. Nothing was compiled or installed.

M1 reports about 14 minutes per track on the authors’ i7; M4 has separate feature-generation and GPU inference timings; M3 trains on an A100. None measures the actual GitHub runner. Stop or reduce scope if a permitted free CPU build/timing probe cannot support even the calibrated baseline, or if the dataset lacks a physically independent test question. Unavailable AMMT access or “data on request” cannot be silently assumed. Any control extension remains simulation-only unless new physical evidence and resources are actually obtained.

## Six-paper independence and decisions still required

The original six-paper requirement is a desired cumulative doctoral structure, not evidence of six publishable units. Neither direction currently supports a six-paper commitment.

| Direction | Consequence for the earlier conditional six slots |
|---|---|
| Contact assembly | Observation/benchmark diagnosis, latent estimation and probe selection will probably belong in one coherent method/validation contribution. New fixtures alone do not create an independent transfer paper. Contact-regime calibration must distinguish A2 and is often part of the same method. Deployment needs resources/evidence that are absent. Merge overlapping slots or abandon them; do not count six variants. |
| LPBF thermal residuals | A “thermal history exists” paper is removed as an originality claim by M1/M2. Residual prediction, adaptive sampling and calibration may be one contribution. Cross-geometry/scan transfer must distinguish M4 and use truly independent physical evidence. Uncertainty/identifiability might earn a separate question only with new evidence. A closed-loop hardware paper is unsupported. |

Retain both as a pair for **evidence verification only**. Contact assembly offers a concrete source-level simulation entry but a severe prior-art and simulator-validity risk. LPBF offers real measurement metadata but unresolved access, independent-unit and model-error risks. The other four batch-2 alternatives have not received this level of reading; this report does not rank them below these two. A formal choice requires the owner’s G1 decision and an honest resource/data protocol; paper questions require G2. No model self-review is substituted for independent criticism.

## Authority, cost and policy carried forward

`project_gateway_calls=0`; `app_session_cost_cny=null`; exact requested/reported API model IDs and native runtime receipt are `null`. The original cumulative API ceiling is CNY 500; unknown prior charges/reservations remain occupied/unknown, with no new per-paper allocation or assumed balance. External paid compute remains USD 0. Actual runner CPU/RAM/time/storage/quota remain unknown. The 2026-10-26 deadline has elapsed; no new date is invented.

Source/version/integrity/privacy/leakage and known access restrictions remain recorded. Licence/research-use checks are optional metadata and create no pre-use human gate. Complete registered, failed and negative comparisons belong in the independent archive; manuscripts/supplements retain material evidence without every raw log. Public AI declarations are optional and author editable; internal provenance remains truthful. Claude’s production role remains read-only and OpenAI/Codex remains the persistent author. Formal project state, G1/G2 approvals and production boundaries are unchanged.
