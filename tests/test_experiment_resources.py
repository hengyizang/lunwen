"""Software resource/deadline controls; no GPU service or scientific job runs."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import cloud_job,cloud_runtime,cloud_research_steps as steps,experiment_runner as runner
from scripts.research_artifacts import read,write,sha
from tests import test_experiment_runner as runner_fixtures


CAPACITY={"cpu":8,"memory_gb":16,"gpu":2,"engine":"docker","container_runtime_verified":True,
          "container_resource_limits_verified":True,
          "gpu_runtime_verified":True,"hardware_provisioned":False,"new_spending_authority":False}


class ExperimentResourceTests(unittest.TestCase):
    def run_spec(self):
        return {"run_id":"probe","paper_id":"P01","argv":["python3","analysis.py"],"cwd":".",
                "seed":0,"timeout_seconds":30,"estimated_cost_usd":0,"inputs":[],
                "expected_outputs":["results/probe.json"],
                "isolation":{"kind":"container","engine":"docker","image":"python@sha256:"+"a"*64}}

    def test_defaults_and_explicit_resources_preserve_the_container_security_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);run=self.run_spec()
            env=runner.safe_environment("probe",0)
            default,_,_=runner.execution_command(project,project,run,env)
            self.assertIn("--cpus=2",default);self.assertIn("--memory=4g",default)
            self.assertNotIn("--gpus",default)
            run["resources"]={"cpu":4,"memory_gb":8,"gpu":2}
            self.assertEqual(runner.resource_errors(run,CAPACITY),[])
            command,_,_=runner.execution_command(project,project,run,env)
            for flag in ("--cpus=4","--memory=8g","--network=none","--read-only","--cap-drop=ALL"):
                self.assertIn(flag,command)
            self.assertEqual(command[command.index("--gpus")+1],"count=2")
            self.assertNotIn("--privileged",command)
            self.assertFalse(any("/dev/" in arg or "GH_TOKEN" in arg for arg in command))

    def test_schema_and_native_validator_reject_unbounded_or_noncontainer_resource_claims(self):
        import jsonschema
        schema=read(Path(runner.ROOT)/"schemas/experiment-plan.schema.json")
        for resources in ({"cpu":0},{"cpu":True},{"memory_gb":-1},{"gpu":True},{"gpu":1.5},
                          {"gpu":-1},{"cpu":"4 --privileged"},{"secret":"not-a-resource"}):
            run=self.run_spec();run["resources"]=resources
            plan={"schema_version":"1.0","status":"ready_for_review","runs":[run]}
            with self.subTest(resources=resources):
                self.assertTrue(runner.validate_plan(plan))
                self.assertTrue(list(jsonschema.Draft202012Validator(schema).iter_errors(plan)))
        for isolation in ({"kind":"host"},{"kind":"git_worktree"},
                          {"kind":"container","engine":"podman","image":"python@sha256:"+"a"*64}):
            run=self.run_spec();run.update(isolation=isolation,resources={"gpu":1})
            self.assertTrue(runner.validate_plan({"schema_version":"1.0","status":"ready_for_review","runs":[run]}))
        for value in (float("inf"),float("nan"),1e308,10**1000):
            run=self.run_spec();run["resources"]={"memory_gb":value}
            self.assertTrue(runner.validate_plan({"status":"ready_for_review","runs":[run]}))

    def test_missing_hardware_is_explicit_and_does_not_enable_a_fallback_executor(self):
        run=self.run_spec();run["resources"]={"cpu":16,"memory_gb":32,"gpu":4}
        errors=runner.resource_errors(run,CAPACITY)
        self.assertTrue(any("16 cpu" in error for error in errors))
        self.assertTrue(any("32 memory_gb" in error for error in errors))
        self.assertTrue(any("4 GPU" in error for error in errors))
        self.assertEqual(run["isolation"]["kind"],"container")
        unknown={**CAPACITY,"gpu":None,"gpu_runtime_verified":False}
        self.assertTrue(runner.resource_errors({**run,"resources":{"gpu":1}},unknown))
        for field in ("cpu","memory_gb"):
            self.assertTrue(runner.resource_errors(self.run_spec(),{**CAPACITY,field:True}))
        self.assertTrue(runner.resource_errors(self.run_spec(),{**CAPACITY,"engine":"podman"}))

    def test_capability_inspection_uses_actual_daemon_and_device_responses_without_credentials(self):
        daemon={"NCPU":4,"MemTotal":8*1024**3,"Runtimes":{"nvidia":{},"runc":{}},
                "MemoryLimit":True,"CpuCfsQuota":True,"CpuCfsPeriod":True}
        responses=[subprocess.CompletedProcess([],0,json.dumps(daemon),""),
                   subprocess.CompletedProcess([],0,"GPU-fixture-a\nGPU-fixture-b\n","")]
        original=Path.read_text
        def source(path,*args,**kwargs):
            if str(path).endswith("cpu.max"):return "800000 100000"
            if "memory" in str(path):return str(16*1024**3)
            return original(path,*args,**kwargs)
        with patch.object(Path,"read_text",source),patch.object(os,"sched_getaffinity",return_value=set(range(8))), \
             patch.object(os,"sysconf",side_effect=lambda key:4096 if key=="SC_PAGE_SIZE" else 4*1024**2), \
             patch.object(runner.shutil,"which",side_effect=lambda name:"/usr/bin/"+name), \
             patch.object(runner.subprocess,"run",side_effect=responses) as inspect, \
             patch.dict(os.environ,{"GH_TOKEN":"synthetic-secret","DOCKER_HOST":"remote-must-not-be-used"}):
            actual=runner.runner_capabilities()
        self.assertEqual((actual["cpu"],actual["memory_gb"],actual["gpu"]),(4,8,2))
        self.assertTrue(actual["container_runtime_verified"] and actual["gpu_runtime_verified"])
        self.assertTrue(actual["container_resource_limits_verified"])
        self.assertFalse(actual["hardware_provisioned"] or actual["new_spending_authority"])
        self.assertNotIn("GPU-fixture",json.dumps(actual))
        for call in inspect.call_args_list:
            self.assertNotIn("GH_TOKEN",call.kwargs["env"])
            self.assertNotIn("DOCKER_HOST",call.kwargs["env"])

    def test_empty_or_malformed_daemon_info_cannot_authorize_container_capacity(self):
        for engine,daemon in (("docker",{}),("docker",{"NCPU":True,"MemTotal":1024}),
                              ("podman",{}),("podman",{"host":None}),
                              ("podman",{"host":{"cpus":4,"memTotal":0}})):
            with self.subTest(engine=engine,daemon=daemon), \
                 patch.object(runner.shutil,"which",side_effect=lambda name:"/usr/bin/"+name if name==engine else None), \
                 patch.object(runner.subprocess,"run",return_value=subprocess.CompletedProcess([],0,json.dumps(daemon),"")):
                actual=runner.runner_capabilities(engine)
                self.assertFalse(actual["container_runtime_verified"])
                self.assertFalse(actual["gpu_runtime_verified"])
                run=self.run_spec();run["isolation"]["engine"]=engine
                self.assertTrue(runner.resource_errors(run,actual))

    def test_cgroup_v1_limits_remain_binding_even_when_podman_exposes_the_whole_host(self):
        files={"/sys/fs/cgroup/cpu/cpu.cfs_quota_us":"50000",
               "/sys/fs/cgroup/cpu/cpu.cfs_period_us":"100000",
               "/sys/fs/cgroup/memory/memory.limit_in_bytes":str(2*1024**3)}
        def source(path,*args,**kwargs):
            if str(path) in files:return files[str(path)]
            raise FileNotFoundError(str(path))
        daemon={"host":{"cpus":8,"memTotal":16*1024**3}}
        with patch.object(Path,"read_text",source),patch.object(os,"sched_getaffinity",return_value=set(range(8))), \
             patch.object(os,"sysconf",side_effect=lambda key:4096 if key=="SC_PAGE_SIZE" else 4*1024**2), \
             patch.object(runner.shutil,"which",side_effect=lambda name:"/usr/bin/podman" if name=="podman" else None), \
             patch.object(runner.subprocess,"run",return_value=subprocess.CompletedProcess([],0,json.dumps(daemon),"")):
            actual=runner.runner_capabilities("podman")
        self.assertTrue(actual["container_runtime_verified"])
        self.assertIsNone(actual["container_resource_limits_verified"])
        self.assertEqual((actual["cpu"],actual["memory_gb"]),(0.5,2))
        self.assertFalse(actual["gpu_runtime_verified"])
        run=self.run_spec();run["isolation"]["engine"]="podman"
        self.assertEqual(len(runner.resource_errors(run,actual)),2)
        run["resources"]={"cpu":0.5,"memory_gb":1.5}
        self.assertEqual(runner.resource_errors(run,actual),[])
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory)
            command,_,_=runner.execution_command(project,project,run,runner.safe_environment("probe",0))
            self.assertIn("--cpus=0.5",command)
            self.assertIn("--memory=1610612736",command)

    def native_fixture(self):
        fixture=runner_fixtures.ExperimentRunnerTests();fixture.setUp();self.addCleanup(fixture.tearDown)
        return fixture.project()

    def seal(self,project,run):
        plan_path=project/"experiments/plan.json";plan=read(plan_path);plan["runs"]=[run];write(plan_path,plan)
        state=read(project/"state/run.json");state["approvals"][0]["experiment_plan_sha256"]=sha(plan_path)
        write(project/"state/run.json",state)

    def test_native_preflight_rejects_insufficient_resources_before_reservation_or_execution(self):
        project=self.native_fixture();run=read(project/"experiments/plan.json")["runs"][0]
        run.update(isolation=self.run_spec()["isolation"],resources={"cpu":32,"memory_gb":64,"gpu":1})
        self.seal(project,run)
        before={name:(project/name).read_bytes() for name in ("experiments/plan.json","experiments/budget.json","state/run.json")}
        with patch.object(runner,"runner_capabilities",return_value=CAPACITY), \
             patch.object(runner.subprocess,"Popen",side_effect=AssertionError("no launch")), \
             patch("scripts.cloud_checkpoint.sync_experiment_reservation",side_effect=AssertionError("no cost reservation")):
            with self.assertRaisesRegex(runner.ExperimentError,"32 cpu"):
                runner.execute("test-phd")
        self.assertFalse((project/"experiments/registry.jsonl").exists())
        self.assertFalse((project/"result.txt").exists())
        self.assertEqual(before,{name:(project/name).read_bytes() for name in before})

    def test_docker_capacity_without_cgroup_support_cannot_reserve_or_execute(self):
        project=self.native_fixture();run=read(project/"experiments/plan.json")["runs"][0]
        run.update(isolation=self.run_spec()["isolation"])
        self.seal(project,run)
        before={name:(project/name).read_bytes() for name in ("experiments/plan.json","experiments/budget.json","state/run.json")}
        daemon={"NCPU":8,"MemTotal":16*1024**3,"MemoryLimit":True,"CpuCfsQuota":True,"CpuCfsPeriod":True}
        for field in ("MemoryLimit","CpuCfsQuota","CpuCfsPeriod"):
            for value in (False,None):
                with self.subTest(field=field,value=value):
                    observed={**daemon,field:value}
                    with patch.object(runner.shutil,"which",side_effect=lambda name:"/usr/bin/docker" if name=="docker" else None), \
                         patch.object(runner.subprocess,"run",return_value=subprocess.CompletedProcess([],0,json.dumps(observed),"")):
                        capabilities=runner.runner_capabilities()
                    self.assertTrue(capabilities["container_runtime_verified"])
                    self.assertFalse(capabilities["container_resource_limits_verified"])
                    with patch.object(runner,"runner_capabilities",return_value=capabilities), \
                         patch.object(runner.subprocess,"Popen",side_effect=AssertionError("no launch")), \
                         patch("scripts.cloud_checkpoint.sync_experiment_reservation",side_effect=AssertionError("no cost reservation")):
                        with self.assertRaisesRegex(runner.ExperimentError,"CPU/memory limits"):
                            runner.execute("test-phd")
        self.assertFalse((project/"experiments/registry.jsonl").exists())
        self.assertFalse((project/"result.txt").exists())
        self.assertEqual(before,{name:(project/name).read_bytes() for name in before})

    def test_resource_edits_invalidate_the_actual_existing_plan_hash(self):
        project=self.native_fixture();plan_path=project/"experiments/plan.json";plan=read(plan_path)
        plan["runs"][0].update(isolation=self.run_spec()["isolation"],resources={"cpu":4})
        write(plan_path,plan)
        with patch.object(runner,"runner_capabilities",side_effect=AssertionError("plan hash is checked first")):
            with self.assertRaisesRegex(runner.ExperimentError,"hash|changed|match"):
                runner.execute("test-phd")

    def test_native_cloud_deadline_failure_happens_before_reserving_the_existing_budget(self):
        project=self.native_fixture();run=read(project/"experiments/plan.json")["runs"][0]
        run.update(isolation=self.run_spec()["isolation"])
        self.seal(project,run)
        budget=(project/"experiments/budget.json").read_bytes()
        with patch.dict(os.environ,{"DR_OS_CLOUD_EXECUTOR":"1","DR_OS_CLOUD_JOB_DEADLINE_EPOCH":"1"}), \
             patch.object(runner,"runner_capabilities",return_value=CAPACITY), \
             patch.object(runner.subprocess,"Popen",side_effect=AssertionError("no launch")), \
             patch("scripts.cloud_checkpoint.sync_experiment_reservation",side_effect=AssertionError("no cost reservation")):
            with self.assertRaisesRegex(runner.ExperimentError,"execution window"):
                runner.execute("test-phd")
        self.assertEqual((project/"experiments/budget.json").read_bytes(),budget)
        self.assertFalse((project/"experiments/registry.jsonl").exists())

    def test_native_software_receipt_does_not_claim_container_limits_or_gpu_use(self):
        project=self.native_fixture()
        result=runner.execute("test-phd")[0]
        self.assertEqual(result["status"],"succeeded")
        allocation=result["resource_allocation"]
        self.assertFalse(allocation["container_limits_configured"])
        self.assertFalse(allocation["actual_resource_use_measured"])
        self.assertIsNone(allocation["observed"])
        self.assertEqual(allocation["requested"],runner.DEFAULT_RESOURCES)

    def test_cloud_deadline_can_support_a_longer_frozen_run_and_expires_honestly(self):
        run=self.run_spec();run["timeout_seconds"]=1800
        with tempfile.TemporaryDirectory() as directory,patch.object(runner,"runner_capabilities",return_value=CAPACITY):
            project=Path(directory)
            with patch.dict(os.environ,{"DR_OS_CLOUD_JOB_DEADLINE_EPOCH":str(time.time()+3000)},clear=True):
                self.assertTrue(steps._cloud_run_eligible(project,run))
            with patch.dict(os.environ,{},clear=True):self.assertFalse(steps._cloud_run_eligible(project,run))
            with patch.dict(os.environ,{"DR_OS_CLOUD_JOB_DEADLINE_EPOCH":"1"},clear=True):
                self.assertFalse(steps._cloud_run_eligible(project,run))
        self.assertEqual(cloud_runtime.execution_window(environment={},current_time=1000)["max_run_timeout_seconds"],1200)
        window=cloud_runtime.execution_window(environment={"DR_OS_CLOUD_JOB_DEADLINE_EPOCH":"4000",
            "DR_OS_CLOUD_COMMAND_DEADLINE_EPOCH":"2500"},current_time=1000)
        self.assertEqual(window["max_run_timeout_seconds"],1380)
        self.assertEqual(cloud_runtime.execution_window(environment={"DR_OS_CLOUD_COMMAND_DEADLINE_EPOCH":"nan"})["max_run_timeout_seconds"],0)

    def test_cloud_command_deadline_does_not_extend_parent_timeout_or_replace_tokens(self):
        with patch.dict(os.environ,{"GH_TOKEN":"synthetic-secret","DR_OS_CLOUD_JOB_DEADLINE_EPOCH":str(time.time()+100)}), \
             patch.object(cloud_job.subprocess,"run",return_value=subprocess.CompletedProcess([],0,"ok","")) as process:
            self.assertEqual(cloud_job.run_command(["scripts/researchctl.py","stages"],timeout=300)[0],0)
            supplied=process.call_args.kwargs
            self.assertLessEqual(supplied["timeout"],100)
            self.assertEqual(supplied["env"]["GH_TOKEN"],"synthetic-secret")
            self.assertLessEqual(float(supplied["env"]["DR_OS_CLOUD_COMMAND_DEADLINE_EPOCH"]),time.time()+100)
        with patch.dict(os.environ,{"DR_OS_CLOUD_JOB_DEADLINE_EPOCH":"1"}),patch.object(cloud_job.subprocess,"run") as process:
            self.assertEqual(cloud_job.run_command(["scripts/researchctl.py","stages"])[0],124)
            process.assert_not_called()

    def test_prepare_records_actual_capacity_requests_and_jsonschema_without_provisioning(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);run=self.run_spec();run["resources"]={"cpu":32,"gpu":1}
            write(project/"experiments/plan.json",{"runs":[run]})
            with patch("scripts.cloud_retry.run",return_value=subprocess.CompletedProcess([],0,"","")), \
                 patch.object(cloud_runtime.importlib.metadata,"version",return_value="software-fixture"), \
                 patch.object(cloud_runtime,"runner_capabilities",return_value=CAPACITY), \
                 patch("scripts.model_runtime.call",side_effect=AssertionError("no paid calls")):
                report=cloud_runtime.prepare(project)
            self.assertEqual(report["available_resources"],CAPACITY)
            self.assertEqual(report["requested_runs"][0]["resources"],{**runner.DEFAULT_RESOURCES,**run["resources"]})
            self.assertTrue(report["requested_runs"][0]["readiness_errors"])
            self.assertIn("jsonschema",report["versions"])
            self.assertFalse(report["model_credentials_in_experiment_environment"])

    def test_prepare_uses_each_requested_container_engine_actual_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);run=self.run_spec();run["isolation"]["engine"]="podman"
            write(project/"experiments/plan.json",{"runs":[run]})
            podman={**CAPACITY,"engine":"podman","cpu":1,"gpu":None,"gpu_runtime_verified":False,
                    "container_resource_limits_verified":None}
            with patch("scripts.cloud_retry.run",return_value=subprocess.CompletedProcess([],0,"","")), \
                 patch.object(cloud_runtime.importlib.metadata,"version",return_value="software-fixture"), \
                 patch.object(cloud_runtime,"runner_capabilities",side_effect=lambda engine="docker":CAPACITY if engine=="docker" else podman):
                report=cloud_runtime.prepare(project)
            self.assertEqual(report["container_engines"]["podman"],podman)
            self.assertIn("exposes 1",report["requested_runs"][0]["readiness_errors"][0])


if __name__=="__main__":unittest.main()
