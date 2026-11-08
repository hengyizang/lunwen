# Second G1 candidate batch: AI interacting with mechanics, robots and manufacturing

**Provenance:** current Codex session draft, exact API model identity unavailable, no native runtime receipt, no topic approval.

Prepared 2026-11-08. The owner rejected the previous three candidates and requested AI combined with mechanical engineering, robotics, manufacturing, mechatronics and autonomous systems. This batch replaces the previous *recommendation for discussion*. It leaves the earlier files intact and does not recycle vehicle-cost analysis, RUL prediction or longitudinal safety-certificate work.

These are six alternative doctoral directions, not six unrelated papers in one thesis. If one is selected, all six eventual papers must answer its one overarching question and earn individual G2 decisions. No candidate has established novelty, six-paper independence, doctoral sufficiency or journal feasibility. The production status supplied for this task is G1 / awaiting_work, with G0 approved and G1/G2 topics undecided; this draft changes no project state.

## 中文概览

这批围绕具体机械对象和可操纵输入，不把“数字孪生”或“LLM机器人”当作题目本身。

| 候选 | AI具体做什么 | 真实物理对象/工程问题 | 当前最值得先核实的风险 |
|---|---|---|---|
| 1. 接触状态感知的机器人精密装配 | 根据力和运动历史学习何时改变柔顺性与微小动作 | 螺母—销/插装任务中的卡滞、摩擦和偏差 | 近邻很拥挤；仿真接触模型可能主导结果 |
| 2. 无人机执行器与扰动的主动辨识控制 | 选择小幅激励，区分电机迟滞、载荷变化和外扰，再调整控制 | 旋翼推力、机体运动与载荷耦合 | 能否从可用传感量辨识，而不是偷看仿真参数 |
| 3. 激光增材制造热记忆的物理约束学习 | 学习热源/热状态残差并选择有信息的扫描工况 | 激光功率、扫描速度、转向间隔与熔池几何 | 简单热传导模型可能已经足够；公开独立试验数未知 |
| 4. 扰动制造车间的学习式重调度 | 学何时重排、何时沿用规则，并与限时求解器配合 | 工序先后、设备占用、换型和临时停机 | 相同可见信息和算力下，强传统方法可能更好 |
| 5. 载荷改变运动约束的多机器人协作 | 学习拥堵引导和优先级，并由运动规划器落实 | 搬运机器人装卸前后的占地、转向和会车 | 含转向/动力学的近邻已存在，不能只加一个约束 |
| 6. 有限元校正的AI机械结构设计 | 学习初始结构或优化更新，再由有限元与约束检查校正 | 承载件的刚度、应力、最小特征尺寸与载荷变化 | CPU训练总成本、网格偏差，以及“换网络”的切香肠风险 |

建议**先查证1和3**：1最直接体现AI与机器人接触控制的交互；3连接机械制造工艺，且已有NIST公开物理测量入口。它们都可能被强基线或最近邻推翻。若首先考虑较轻的CPU试点，4是资源上更保守的备选；这不是七项权重的综合排名，也不代替你的选题决定。

## Evidence and execution boundaries

The original intake and all copied metadata were read in the first draft. The researcher reports mechanical-engineering, Big Data/BI and AI4Health study, Python/data analysis and engineering-software experience. Exact credentials and control/finite-element proficiency remain unverified. This batch follows the owner's more specific new preference; no robotics laboratory, GPU, robot, drone or machine tool is assumed to exist.

The seven weights remain: funded-position supply 25%; employment/salary 25%; future growth 15%; PhD competition 7.5%; job competition 7.5%; background fit 10%; application-route fit 10%. We collected no new eligible-position, salary, competition or admission-regulation evidence. Consequently, no numerical scores, weighted winner, funded-place counts or employment claims are supplied. In particular, missing factors must not be renormalized away.

The cumulative project model/API ceiling is still **CNY 500**, with previous unknown charges/reservations preserved. `project_gateway_calls = 0`; `app_session_cost_cny = null` for this drafting task. The external paid-compute envelope is **USD 0**. Actual runner CPU count, RAM, available minutes, storage and package-installation performance have not been supplied in this evidence packet. All probe sizes below are proposed measurement bounds, not measured feasibility, financial allocations or additional per-paper limits. No simulation, installation, training or data download was executed.

This follow-up used **18 public-source commands**, counting eight searches, nine web opens and one failed read-only GitHub fetch. One GitHub fetch failed because no file SHA was returned; a browser-source fallback found the repository redirect. A subsequent AAAI open was blocked by an anti-bot access-denied page. Both failures remain in the notes; no control was bypassed. Some sources were read as actual abstract pages, others only as indexed abstract/method excerpts. **No complete paper or supplementary method package was read.** These are located recent neighbors, not a completed originality audit or systematic review.

The original 2026-10-26 deadline has passed; no replacement date or six-paper delivery promise is inferred. Public or already authorized inputs are required. Source/version, privacy, integrity, leakage and known access restrictions remain; licence/research-use checks are optional metadata and create no new human pre-use gate. Full outcomes and failed/registered comparisons belong in the independent archive, while material evidence remains in papers/supplements. Public AI-use statements remain author-editable. Production Claude/OpenAI role boundaries, actual model identity checks, independent criticism, G1/G2 decisions and the experiment runner remain unchanged.

## 1. Contact-state-aware learning for precision robotic assembly

**Physical object + AI mechanism.** A robot inserts a nut over a peg or a peg into a hole. A small recurrent/latent-state estimator or probabilistic contact-mode model uses end-effector pose/velocity and simulated wrist-wrench history to choose bounded pose increments and compliance settings. The AI must reason about contact transitions, not merely map images to an action.

**Discriminating doctoral question.** Can a representation learned from observable contact histories identify when to change compliance or search direction across unseen clearance/friction combinations, beyond what a tuned force/position controller and geometric search already achieve?

**Pilot title:** *Does Contact History Improve Assembly Control Beyond Tuned Compliance and Geometric Search?*

**Located research and baselines.**

- [Focus-Then-Contact, ICML 2026](https://proceedings.mlr.press/v306/qiao26f.html): actual abstract page read. It already combines residual RL, affordance-guided rewards and force-control feedback for contact-rich tasks.
- [VT-Refine, CoRL 2025](https://proceedings.mlr.press/v305/huang25b.html): indexed abstract/method excerpts read. It combines real demonstrations, tactile simulation and reinforcement learning for bimanual assembly.
- [Force Policy, RSS 2026](https://www.roboticsproceedings.org/rss22/p128.html): title and indexed excerpt read; it explicitly concerns hybrid force/position control and interaction frames.

A generic residual policy, tactile feedback addition or assembly success gain is therefore not an established new contribution. The focal difference would have to be an observable, transferable mechanism for contact-transition decisions, confirmed against these methods rather than inferred from their titles.

**Reproducible input path.** [robosuite documentation, displayed version 1.5](https://robosuite.ai/docs/modules/environments.html) explicitly provides Nut Assembly and Two Arm Peg-In-Hole tasks, object/proprioceptive observations and a mode with both renderers and camera observations disabled. That supports a low-dimensional simulation entry. The exact release/commit, MuJoCo version, scene XMLs, contact solver settings and required wrench instrumentation are not frozen or downloaded. Ideal simulated forces must be labeled as such; no real tactile dataset or measured hardware robustness is implied.

**Small falsification trial.** Begin with one single-nut task, known goal pose and a predeclared grid of clearance, initial misalignment and friction. Compare fixed tuned compliance plus spiral/search motion, a memoryless learned controller, and the history-aware controller. Train only on a small declared subset and hold out complete geometry/parameter combinations. Plot completion, peak force, jamming and interaction count together; do not hide force escalation behind success rate.

If removing history leaves performance unchanged, or a gain disappears when controller tuning/search exposure is matched, the proposed contact-memory mechanism is unsupported. If a gain disappears under a second plausible contact-parameter setting or smaller simulation timestep, revise the claim before expanding the policy.

**Independent units, leakage and strongest rival.** Units are independent assembly episodes grouped by geometry/contact-parameter family. Frames from the same episode are not independent replicates. Hold out hole/peg geometry families, not merely new random seeds of the same mesh. The policy must not receive hidden friction, a ground-truth “jammed” flag or a simulator success oracle as an observation. The strongest practical rival is well-tuned classical compliance plus deliberate geometric search; oracle-contact-state control is an upper-bound diagnostic, not a fair baseline.

**CPU/resource boundary and stop line.** Start headless with a small estimator and hundreds, not millions, of short rollouts. First measure one 30-minute probe and peak memory under a declared single-job configuration. Stop expansion if meaningful learning requires large visual/tactile encoders, long RL training, unprovided human demonstrations or robot experiments. A simulator-only paper must make simulator-scoped claims; future laboratory access cannot substantiate it.

**Six-paper thesis map and fragmentation risk.** One overarching question: *which contact information enables reliable assembly decisions under mechanical uncertainty?* Core A could examine (P01) contact-state observability, (P02) a structured estimator and (P03) control decisions conditioned on its uncertainty. Extension B could independently examine (P04) geometric/material transfer, (P05) active probing for ambiguous contact and (P06) coordinated assembly under bounded sensing. B needs independent geometry/contact cases and its own hypotheses, rather than reuse favorable P02 predictions. P01–P03 may belong in one strong paper; P04–P06 risk becoming task variants. The field is crowded and six independent contributions are unproved.

## 2. Active identification of actuator dynamics and disturbances in aerial mechatronics

**Physical object + AI mechanism.** A quadrotor with rotor-command lag, changing mass/inertia and aerodynamic disturbance. A physics-structured residual model or Bayesian latent dynamics estimator proposes small informative excitation maneuvers, then adapts trajectory control. Inputs are causal state/IMU estimates and command history; motor effectiveness and wind are hidden.

**Discriminating doctoral question.** When can limited, physically admissible excitation distinguish a change in command-to-thrust dynamics from an external force or payload change, and does that distinction improve control more than an aggregate disturbance estimate?

**Pilot title:** *Can Small Excitation Maneuvers Separate Rotor Lag from External Disturbance in Learned Quadrotor Control?*

**Located research and baselines.**

- [Adaptive Outer-Loop Control of Quadrotors via Reinforcement Learning, 2026](https://arxiv.org/abs/2605.16015): indexed abstract read. It already uses state/action history to predict residual forces/moments and describes thrust correction.
- [Learned Incremental Nonlinear Dynamic Inversion for Quadrotors with and without Slung Payloads, L4DC 2026](https://proceedings.mlr.press/v331/cobo-briesewitz26a.html): indexed abstract read. It replaces or complements residual-force estimation with learned predictions.
- [Proto-MPC, L4DC 2024](https://proceedings.mlr.press/v242/gu24a.html): indexed abstract/method excerpt read. It addresses learned residual adaptation for tracking in challenging winds.

These are strong reasons not to claim novelty for “AI adapts a drone to wind/payload.” Active identifiability under actuator/force ambiguity is the narrower hypothesis to test. Its overlap with adaptive control and experiment-design literature remains unresolved.

**Reproducible input path.** The public [gym-pybullet-drones README](https://github.com/learnsyslab/gym-pybullet-drones/blob/main/README.md), reached by redirect from utiasDSL, was read. It lists PID, velocity-PID and MRAC examples and describes a PyBullet-based environment. The default branch is mutable; no exact commit or package installation was verified. Its README warns that recent Python versions may need a local PyBullet build. Rotor lag/payload mechanisms required by this question must be checked or implemented as explicit, reviewed model extensions. The current environment must not be assumed to model them already.

**Small falsification trial.** Use a single simulated vehicle and simple hover-to-translation reference. Construct two parameter/disturbance settings that are indistinguishable or nearly indistinguishable during passive hover. Compare no excitation, a fixed small excitation, and an information-seeking policy while matching flight-envelope and control-effort limits. Evaluate identification error, held-out trajectory tracking, saturation and adaptation transients.

If aggregate disturbance rejection or ordinary recursive identification performs equally well, separating the latent causes has not earned its complexity. If the causes remain unidentifiable with available observations, that is a possible bounded negative/formal result; it does not justify claiming successful adaptation. Excitation must not be counted as useful merely because it leaves the operational envelope.

**Independent units, leakage and strongest rival.** Units are complete flights grouped by vehicle-parameter and disturbance families. Windows from the same flight stay together. Simulator wind, true rotor lag, exact mass and unfiltered future acceleration are not policy inputs. Compare against a strong model-based/adaptive controller such as MRAC or an appropriate disturbance-observer/INDI implementation with the same sensors and tuning budget. A model trained with privileged parameters must be labeled separately.

**CPU/resource boundary and stop line.** Use one vehicle, low-dimensional features and small closed-form/linear-in-feature updates first. Measure a 30-minute headless probe, including dependency build overhead, rather than assume a free high-speed physics engine. Stop if learning requires large-scale policy training, the actuator model cannot be validated even internally, or the important conclusion needs real flight data not publicly available. No physical drone or motion-capture system is assumed.

**Six-paper thesis map and fragmentation risk.** One question: *how does information acquisition improve adaptive control of an uncertain aerial electromechanical system?* Possible core A: (P01) actuator/force identifiability, (P02) physics-structured latent modeling, (P03) informative but bounded excitation. Possible extension B: (P04) changing-payload dynamics, (P05) sensor/actuation delay interaction and (P06) multi-timescale adaptation under independent parameter/disturbance families. B must retain value if cause separation proves impossible, for example by deriving when aggregate adaptation is sufficient. P02/P03 and P04/P06 could merge. Multiple disturbance types alone do not create multiple papers; current related work makes novelty risk substantial.

## 3. Physics-constrained learning of thermal memory in laser additive manufacturing

**Physical object + AI mechanism.** A laser scans a metal surface during powder-bed-fusion-relevant experiments. Power, scan speed, track order and inter-track pause change heat accumulation and melt-pool shape. A heat-equation baseline plus a small learned heat-source/residual model uses these inputs and previous-track thermal state; an active selection rule chooses informative scan conditions.

**Discriminating doctoral question.** Does explicitly learning the interaction between scan history and heat-source uncertainty improve prediction and scan-setting decisions on unseen scan protocols, beyond energy-density features and a calibrated transient-conduction model?

**Pilot title:** *Does Learned Thermal Memory Add Value Beyond Transient Diffusion for Rapid-Turnaround Laser Scans?*

**Located research and baselines.**

- [Physics guided heat source for quantitative prediction of IN718 laser additive manufacturing processes, 2024](https://www.nature.com/articles/s41524-024-01198-6): indexed method/abstract excerpts read; it concerns heat-source parameterization and AM-Bench thermal/melt-pool targets.
- [The trace of heat, 2025](https://www.nist.gov/publications/trace-heat-predictive-power-modeling-transient-diffusion): actual NIST abstract read. It reports that a transient diffusion/phase-change model captures rapid-turnaround melt-pool effects and examines feedforward scan modification.
- [Toward The Realtime Feedback Control for Powder Bed Fusion Additive Manufacturing, 2025](https://www.nist.gov/publications/toward-realtime-feedback-control-powder-bed-fusion-additive-manufacturing): indexed NIST abstract/excerpt read; it studies laser-power feedback using melt-pool area.

The second work is particularly strong counterevidence to an automatic claim that a large AI model is needed. A useful contribution must show exactly which residual interaction remains after a credible physics baseline and whether that interaction changes a process decision.

**Reproducible input path.** [NIST AM-Bench](https://www.nist.gov/ambench) states that measurements are permanently archived for public use and links its data/challenge problems. The 2018/2022/2025 series is an entry point, not one interchangeable dataset. Exact measurement publication, alloy, specimen, scan files, uncertainty estimates, access route and downloadable size remain unverified. Some 2025 final data publications were still described as being finished on the page read. Select existing published scalar melt-pool/thermal measurements before considering raw image volumes. No printer, camera or new physical experiment is assumed.

**Small falsification trial.** Select one documented alloy/benchmark and two scan-history regimes with comparable nominal energy input, if the actual data contain them. Fit an energy-density baseline, a calibrated heat-diffusion/phase-change baseline and a physics-plus-small-residual model with identical available calibration scans. Hold out entire scan protocols. Compare melt-pool geometry/thermal targets with their measurement uncertainty and assess whether a recommended pause/power change remains consistent with held-out measurements.

If diffusion alone explains the observed differences within measurement uncertainty, reject the claimed need for a learned memory correction. If the AI gains only by receiving withheld thermal state or by mixing frames from the same scan into train/test, the result is invalid. A proposed scan setting is not experimentally validated unless existing measurements actually cover it.

**Independent units, leakage and strongest rival.** Group by specimen/build and scan protocol, with tracks nested within them; pixels and temperature samples are not separate experiments. If only one build is available, restrict inference to that benchmark rather than claim machine/alloy transfer. The strongest rival is an accurately calibrated transient heat-conduction model with temperature-dependent coefficients and phase change—not just a linear regression on energy density.

**CPU/resource boundary and stop line.** Begin with a reduced moving-heat-source/conduction model, tabular measurements and a small GP/basis residual. Resolve mesh/time-step convergence at a modest scale before any machine learning comparison. A 60-minute resource probe should report simulation and fit time separately. Stop if the claimed endpoint requires full melt-pool CFD, large 3-D training, unpublished build data, microstructure prediction without relevant measurements, or experimental closed-loop control on unavailable hardware. Thermal prediction does not itself establish defect rate, part strength or industrial control performance.

**Six-paper thesis map and fragmentation risk.** One question: *which learned corrections to physically modeled thermal memory produce transferable scan-process decisions?* Core A might comprise (P01) separating history effects from energy-density effects, (P02) identifiable heat-source/residual learning and (P03) informative scan-condition selection. Extension B might comprise (P04) transfer across an independently measured geometry/alloy regime, (P05) uncertainty-aware scan-setting selection and (P06) thermal-history feedback under a separate observed scan family. B needs independent measurements and cannot be a second fit to the same few tracks. P01–P03 may be one paper; P05/P06 may require unavailable physical feedback. Six cloud-only papers are not established. This candidate should be discarded or narrowed if available public evidence cannot support the proposed extension.

## 4. Learning when to reschedule a disturbed manufacturing cell

**Physical object + AI mechanism.** Jobs pass through specific machines with precedence, processing-time, availability and possibly sequence-dependent changeover constraints. A small graph/context model learns when to keep the current dispatch plan, switch a dispatch rule or request a bounded local optimization step. It addresses decision timing and physical feasibility instead of “a GNN solves scheduling.”

**Discriminating doctoral question.** Under causal event visibility and the same decision-time compute budget, can learned rescheduling triggers reduce disruption-induced lateness and schedule churn beyond event-driven heuristics and periodically rerun CP-SAT?

**Pilot title:** *When Is Learning to Reschedule Better Than Event-Driven Dispatch and Bounded Optimization?*

**Located research and baselines.**

- [DynaSchedBench, ICML 2026](https://proceedings.mlr.press/v306/cao26z.html): indexed abstract read. It explicitly concerns controlled dynamic flexible-job-shop generation and the information shown to agents.
- [RESCHED, 2026](https://arxiv.org/abs/2603.07020): indexed abstract read. It studies simplified scheduling state and transformer-based policies; its abstract does not establish a solution to this candidate's dynamic trigger question.
- [Policy-Based Reinforcement Learning with Action Masking for Dynamic Job Shop Scheduling under Uncertainty, 2026](https://arxiv.org/abs/2601.09293): indexed abstract read. It already includes random arrivals, failures, a Petri-net environment and masked policy learning.

The first source's discussion of LLM agents is not a reason to add an LLM here. Dynamic RL, masking and another dispatch network are already occupied territory.

**Reproducible input path.** [JobShopLib documentation, displayed version 1.7.2](https://job-shop-lib.readthedocs.io/en/stable/) exposes benchmark loading, seeded instance generation, dispatch rules, graph representations and OR-Tools CP-SAT. A static benchmark is not a real dynamic factory log. A documented discrete-event wrapper must define arrival revelation, downtime, operation interruption and setup semantics; flexible routing/changeovers must not be assumed to be implemented by the shown examples. No factory data or physical production line is required for explicitly synthetic claims.

**Small falsification trial.** Use a small job-shop instance family, with independently generated event streams for training and testing. Compare a fixed dispatch rule, an event-triggered heuristic, periodic local CP-SAT and a learned trigger/selector. Give all policies the same currently visible jobs/events and the same total decision-time budget. Include a matched no-disturbance condition and a disturbance regime outside training. Measure tardiness, makespan, rescheduling churn, infeasible decisions and complete wall time.

If learned triggering is no better after observation and compute are matched, or the gain comes only from knowing future breakdown/recovery times, stop that mechanism. If improvement is confined to one generator, do not call it industrial generalization.

**Independent units, leakage and strongest rival.** Units are full independently generated production instances/event streams, blocked by routing and disturbance family. Different snapshots of the same shop rollout belong to one unit. Future processing outcomes, failure end times and unreleased orders are not current observations unless explicitly available in the stated setting. The strongest rival is well-configured event-driven rescheduling with an efficient bounded classical solver, not a weak shortest-processing-time rule alone.

**CPU/resource boundary and stop line.** Start with small shops and a light selector; cap the first resource probe at 30 minutes and record per-decision solver time. Do not train a large transformer or require a paid LLM scheduling service. Stop if fair baseline tuning already exhausts the included runner budget, if the simulator cannot enforce stated physical constraints, or the contribution reduces to an architecture change on the same benchmark. Resource/observation restrictions must be common to every method.

**Six-paper thesis map and fragmentation risk.** One question: *when should a manufacturing controller spend effort changing its schedule under partially revealed disturbances?* Core A could cover (P01) causal observability and trigger value, (P02) a budgeted learning–optimization selector and (P03) schedule stability under setup/queue interactions. Extension B could cover (P04) censored/uncertain processing completion, (P05) transfer to independently generated routing/arrival families and (P06) a theoretically grounded bound or mechanism for replan frequency and disruption amplification. This is manufacturing operations, not RUL estimation. Different failure rates or shop sizes do not justify separate papers. P01/P02 and P03/P06 may merge; the scheduling literature is very crowded and real-factory external validity remains absent.

## 5. Load-dependent motion and learned coordination for warehouse robots

**Physical object + AI mechanism.** Differential-drive transport robots repeatedly pick up/drop off loads. The load can change footprint and allowable turning/acceleration, so an otherwise short grid path may cause blocking or become physically infeasible. A small learned guidance/priority model supplies congestion costs to an explicit kinodynamic planner.

**Discriminating doctoral question.** Does conditioning coordination on changes in payload-dependent footprint and maneuver time improve warehouse throughput and fairness beyond kinodynamically feasible search and adaptive traffic guidance alone?

**Pilot title:** *Does Load-Dependent Maneuver Modeling Change the Value of Learned Warehouse-Robot Guidance?*

**Located research and baselines.**

- [Online Guidance Graph Optimization for Lifelong MAPF, AAAI 2025](https://ojs.aaai.org/index.php/AAAI/article/view/33614): indexed abstract read; guidance is already adapted to real-time traffic and changing task distributions.
- [Multi-Agent Motion Planning for Differential Drive Robots Through Stationary State Search, AAAI 2025](https://ojs.aaai.org/index.php/AAAI/article/view/34503): indexed abstract read; it already addresses orientation, speed/acceleration and kinodynamic feasibility. Direct page opening later returned access denied; its full methods were not read.
- [Search-Aided Joint Agent-Environment Reinforcement Learning for Robust Lifelong MAPF with Rotations, 2026](https://arxiv.org/abs/2608.05588): indexed abstract read. It already combines learned guidance, search, robustness and rotation constraints.

“Make MAPF realistic by adding rotation” is not a new gap. The unresolved difference is changing payload geometry/maneuverability and whether learning adds value beyond a correctly modeled search baseline. It may turn out to be only an incremental constraint extension.

**Reproducible input path.** The [MovingAI MAPF benchmark page](https://movingai.com/benchmarks/mapf/index.html) exposes maps and scenario downloads, including warehouse maps and small empty/maze cases. It includes a historical map correction, illustrating why files must be hashed. These are maps/start-goal scenarios, not measured robot dynamics or warehouse operations. A separate declared model must assign footprints, turn/acceleration bounds, pickup/dropoff transitions and task arrivals. Exact files, units-to-meters convention and dynamics parameters remain unverified; no hardware is available by assumption.

**Small falsification trial.** Use a bottleneck map and a second distinct map with a small fleet, initially around 8–16 simulated robots. Cross loaded/unloaded footprint changes with task streams. Compare a static traffic rule, strong feasible search, adaptive non-learned guidance and learned guidance, all using the same physical constraints and decision-time budget. Test on maps/task distributions held out at training.

If the learned advantage vanishes once every baseline models load footprint and maneuver time correctly, the claimed AI benefit fails. If throughput rises by starving some robots, hiding deadlocks or allowing overlapping swept footprints, it fails on the stated problem. Realistic action execution must follow the planner's maneuver durations rather than a simultaneous unit-step cartoon.

**Independent units, leakage and strongest rival.** Units are whole map/task-stream/dynamics-family runs. Individual agents sharing one congested run are dependent. Hold out map families, not just random starts on the same warehouse. Future task destinations, true future travel time and global information unavailable under the declared communication model are not observations. The strongest rival is a well-tuned kinodynamic/lifelong search method with adaptive guidance; named recent methods must be compared fairly or their unreproduced-baseline gap disclosed.

**CPU/resource boundary and stop line.** Begin with small fleets, low-dimensional guidance weights and compiled/classical search where available. Measure a 30-minute CPU probe, including worst-case congestion and timeouts. Stop if a credible comparison requires large multi-agent RL training or unprovided pretrained policies, if geometry/motion checking dominates available resources, or if payload changes create no separate mechanism beyond known constraints. No physical fleet or mixed-reality deployment is claimed.

**Six-paper thesis map and fragmentation risk.** One question: *how should coordination exploit knowledge of changing robot maneuverability during repeated transport?* Core A might address (P01) load/maneuver bottleneck mechanisms, (P02) physically conditioned guidance and (P03) task-allocation/traffic coupling. Extension B might address (P04) heterogeneous loaded robots, (P05) communication-limited adaptation and (P06) deadlock recovery with independent map/task families and a new analysis or algorithm. Payload size, fleet size and map substitutions alone are not independent contributions. P02/P03 and P04/P05 could collapse. Current neighbors already cover much of the obvious scope, making a six-paper claim especially premature.

## 6. Finite-element-corrected AI for constrained mechanical structural design

**Physical object + AI mechanism.** A load-bearing planar bracket/continuum structure is represented by material density or a small geometric parameterization. A compact learned model proposes a warm start or optimization update from boundary conditions and coarse physical fields; an independent finite-element solver evaluates equilibrium, stiffness and carefully defined stress/feature constraints.

**Discriminating doctoral question.** Can a small physics-conditioned proposal model reduce total design cost on unseen load/support families while retaining final mechanical feasibility, once training data, correction solves and mesh effects are fully counted?

**Pilot title:** *Do Learned Topology Warm Starts Still Save Work After Finite-Element Correction and Boundary-Condition Transfer?*

**Located research and baselines.**

- [Stress-constrained optimization of multiscale structures with parameterized microarchitectures using machine learning, 2024](https://link.springer.com/article/10.1007/s00158-024-03821-y): indexed abstract/method excerpt read. It already uses neural constitutive surrogates within constrained structural optimization.
- [Diffusion transformers with hybrid conditioning for structural optimization, 2026](https://link.springer.com/article/10.1007/s00158-026-04429-0): indexed method excerpts read; they describe SIMP-generated conditioning data, boundary/load variation and stress/strain fields. Its full abstract/methods were not read.
- [Scalable Stress-Constrained Topology Optimization, 2026](https://arxiv.org/abs/2610.28703): indexed abstract read. It describes simultaneous neural state/adjoint/design learning and large multi-GPU cases.

These make another neural topology predictor insufficient as a novelty claim. This candidate deliberately asks about the remaining advantage of a small CPU-scale proposal after correction and honest total-cost accounting, not reproducing a large generative model.

**Reproducible input path.** [DTU's public Python TopOpt page](https://www.topopt.mek.dtu.dk/apps-and-software/topology-optimization-codes-written-in-python) supplies an educational NumPy/SciPy topology-optimization entry and identifies its relationship to the 2011 88-line method. That is a transparent classical starting point, not a verified stress-constrained production solver. Exact code bytes/version, mesh convention and numerical checks are not yet frozen. A stress-constrained extension needs its own reviewed formulation; the public compliance example must not be relabeled as one.

**Small falsification trial.** Start with a small 2-D linear-elastic mesh, distributed loads and a few distinct support/load families. Generate a bounded reference set using a classical method, split complete boundary-condition families, and compare a uniform start, nearest-neighbor/reused classical design and a compact learned proposal followed by the same correction solver. Count all training-generation, fitting, finite-element and repair costs. Verify final designs on a refined mesh.

If correction removes the speed advantage, nearest-neighbor starts match the neural model, or final designs violate the same constraints, the claimed benefit fails. A visually similar structure is not equivalent mechanical performance. Avoid reporting a mesh-dependent point-load singularity as a meaningful maximum-stress comparison; the stress functional and load application need an explicit physical definition.

**Independent units, leakage and strongest rival.** Units are independently specified geometry/boundary/load problems, grouped by family. Elements, pixels and optimizer iterations are not independent examples. Re-meshing the same problem across train/test is leakage. Ground-truth optimized stress/topology from a test problem cannot be supplied as a deployment input. The strongest rival is a tuned classical solver with continuation/warm starts and a simple similarity-based retrieval scheme.

**CPU/resource boundary and stop line.** Start near a 32-by-16 element educational problem, a compact proposal model and at most a small declared batch of reference cases, then measure one 60-minute resource probe. This is a probe scale, not a doctoral-quality evidence scale. Stop if meaningful comparisons require large training corpora, multi-GPU super-resolution, commercial FE software or unprovided experimental material tests. Computational feature-size constraints do not establish as-manufactured strength.

**Six-paper thesis map and fragmentation risk.** One question: *when can learned proposals accelerate mechanically constrained design beyond reusable classical optimization?* Core A could examine (P01) the source of warm-start advantage, (P02) solver-coupled proposals and (P03) out-of-family boundary/load transfer with correction. Extension B could examine (P04) geometric tolerance/minimum-feature robustness, (P05) independently defined multi-load or elastic-regime tasks and (P06) information-efficient reference generation with a distinct mechanical/computational result. P01–P03 could be one benchmark/method paper; P04/P05 may be a routine constraint extension. A full six-paper programme cannot be inferred from a low-resolution demonstration, and the field is highly competitive.

## Evidence to resolve before comparing or choosing

For **1**, inspect full force/compliance/residual-policy methods and freeze a headless contact scene; the first scientific test is whether contact history matters after tuning and contact-model checks. For **3**, identify exact downloadable measurements and independent scan/build units, then test the credible diffusion baseline before building a larger learned model. These are the two recommended first investigations on fit and problem concreteness alone.

The other candidates are retained alternatives, not rejected by an invented score. **4** offers the most direct small discrete-event CPU experiment, **6** a transparent mechanics/FE route with a substantial training-cost trap, **2** a control/identifiability route needing stronger dynamics expertise, and **5** an autonomy/coordination route whose obvious novelty space is already crowded.

Before any native G1 decision, the project still needs full source-bound candidate differences, actual scientific independent critique, immutable datasets/simulators, a measured resource test and a defensible six-paper dependency/contribution map. It also needs the missing dated, eligibility-aware funding/employment/competition/route evidence to apply the owner's seven weights. A completed template or successful software run establishes none of these scientific conclusions.

