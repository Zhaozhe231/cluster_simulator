"""模拟引擎测试"""

import pytest
import sys
import os

from task import Task, TaskType, TaskStatus
from machine import Machine, MachineState, REPAIR_DURATION
from scheduler import SchedulePolicy
from simulator import Simulator, SimConfig, MINUTES_PER_DAY, MORNING_8AM
from metrics import MetricsCollector


# ==================== 正向流程 ====================

class TestSimulatorNormal:
    def test_basic_run_completes(self):
        """基础模拟能正常运行完毕"""
        config = SimConfig(num_machines=5, sim_days=1, seed=42)
        sim = Simulator(config)
        metrics = sim.run()
        assert metrics is not None
        assert len(metrics.completed_tasks) > 0

    def test_all_tasks_generated(self):
        """预生成的任务数量正确"""
        config = SimConfig(num_machines=5, sim_days=3,
                           normal_tasks_per_day=10, priority_tasks_per_day=0,
                           failure_prob_per_machine_per_day=0, seed=1)
        sim = Simulator(config)
        total_tasks = sum(len(v) for v in sim.task_arrivals.values())
        assert total_tasks == 30  # 10 * 3 天

    def test_normal_tasks_arrive_at_8am(self):
        """普通任务只在8:00到达"""
        config = SimConfig(num_machines=5, sim_days=2,
                           normal_tasks_per_day=5, priority_tasks_per_day=0,
                           failure_prob_per_machine_per_day=0, seed=1)
        sim = Simulator(config)
        for arrival_time, tasks in sim.task_arrivals.items():
            for t in tasks:
                if t.task_type == TaskType.NORMAL:
                    assert arrival_time % MINUTES_PER_DAY == MORNING_8AM

    def test_no_failure_means_no_interruptions(self):
        """故障率为0时不应有任务中断"""
        config = SimConfig(num_machines=5, sim_days=2,
                           failure_prob_per_machine_per_day=0, seed=1)
        sim = Simulator(config)
        metrics = sim.run()
        preemptions = [e for e in metrics.events if e["type"] == "task_preempted"]
        assert len(preemptions) == 0

    def test_completed_tasks_have_valid_times(self):
        """已完成任务的时间字段应合法"""
        config = SimConfig(num_machines=10, sim_days=2, seed=42)
        sim = Simulator(config)
        metrics = sim.run()
        for t in metrics.completed_tasks:
            assert t.status == TaskStatus.COMPLETED
            assert t.finish_time >= t.start_time >= 0
            assert t.finish_time >= t.arrival_time
            assert t.turnaround_time >= 0
            assert t.remaining_time == 0

    def test_deterministic_with_same_seed(self):
        """相同种子产生相同结果"""
        config1 = SimConfig(num_machines=5, sim_days=2, seed=123)
        config2 = SimConfig(num_machines=5, sim_days=2, seed=123)
        sim1 = Simulator(config1)
        m1 = sim1.run()
        sim2 = Simulator(config2)
        m2 = sim2.run()
        assert len(m1.completed_tasks) == len(m2.completed_tasks)
        for t1, t2 in zip(m1.completed_tasks, m2.completed_tasks):
            assert t1.task_id == t2.task_id
            assert t1.finish_time == t2.finish_time

    def test_different_seeds_differ(self):
        """不同种子产生不同结果"""
        config1 = SimConfig(num_machines=5, sim_days=3, seed=1)
        config2 = SimConfig(num_machines=5, sim_days=3, seed=999)
        sim1 = Simulator(config1)
        m1 = sim1.run()
        sim2 = Simulator(config2)
        m2 = sim2.run()
        # 任务数大概率不同（因泊松分布随机数不同）
        ids1 = {t.task_id for t in m1.completed_tasks}
        ids2 = {t.task_id for t in m2.completed_tasks}
        # 至少完成时间分布不一样
        times1 = [t.finish_time for t in m1.completed_tasks]
        times2 = [t.finish_time for t in m2.completed_tasks]
        assert times1 != times2

    def test_machine_failure_and_recovery(self):
        """有故障时机器能正确恢复"""
        config = SimConfig(num_machines=3, sim_days=3,
                           failure_prob_per_machine_per_day=0.5,  # 高故障率
                           seed=42)
        sim = Simulator(config)
        metrics = sim.run()
        failures = [e for e in metrics.events if e["type"] == "machine_failed"]
        repairs = [e for e in metrics.events if e["type"] == "machine_repaired"]
        assert len(failures) > 0
        # 每次故障最终都应恢复（如果模拟时间足够长）
        # 至少部分故障已恢复
        assert len(repairs) > 0

    def test_all_policies_run(self):
        """所有策略都能正常运行"""
        for policy in SchedulePolicy:
            config = SimConfig(num_machines=5, sim_days=1,
                               schedule_policy=policy, seed=42)
            sim = Simulator(config)
            metrics = sim.run()
            assert len(metrics.completed_tasks) >= 0


class TestSimulatorMachineFailure:
    def test_interrupted_task_returns_to_queue(self):
        """机器故障时运行中的任务应回到队列"""
        config = SimConfig(num_machines=2, sim_days=2,
                           failure_prob_per_machine_per_day=0.3,
                           normal_tasks_per_day=5, priority_tasks_per_day=2,
                           seed=7)
        sim = Simulator(config)
        metrics = sim.run()
        preemptions = [e for e in metrics.events if e["type"] == "task_preempted"]
        # 如果有抢占事件，被抢占的任务应最终完成或还在队列中
        for evt in preemptions:
            tid = evt["task_id"]
            task = sim.all_tasks[tid]
            assert task.status in (TaskStatus.COMPLETED, TaskStatus.WAITING,
                                   TaskStatus.RUNNING)


# ==================== 异常输入 ====================

class TestSimulatorAbnormal:
    def test_zero_tasks(self):
        """0个任务的模拟应正常完成"""
        config = SimConfig(num_machines=5, sim_days=1,
                           normal_tasks_per_day=0, priority_tasks_per_day=0,
                           failure_prob_per_machine_per_day=0, seed=1)
        sim = Simulator(config)
        metrics = sim.run()
        assert len(metrics.completed_tasks) == 0
        assert metrics.unfinished_running == 0
        assert metrics.unfinished_waiting == 0

    def test_single_machine(self):
        """1台机器也能正常运行"""
        config = SimConfig(num_machines=1, sim_days=2,
                           normal_tasks_per_day=3, priority_tasks_per_day=1,
                           seed=42)
        sim = Simulator(config)
        metrics = sim.run()
        assert len(metrics.completed_tasks) > 0

    def test_very_short_simulation(self):
        """只模拟几个小时（不足1天不会触发日结打印）"""
        config = SimConfig(num_machines=5, sim_days=1,
                           normal_tasks_per_day=2, priority_tasks_per_day=0,
                           failure_prob_per_machine_per_day=0, seed=1)
        sim = Simulator(config)
        # 手动只跑到中午
        for t in range(12 * 60):
            sim.current_time = t
            sim._step_repair_check()
            sim._step_task_completion()
            sim._step_failure_check()
            sim._step_task_arrival()
            sim._step_schedule()
        # 8:00到达的2个任务应该已完成（最长180分钟，12:00前够了）
        completed = [t for t in sim.all_tasks.values() if t.status == TaskStatus.COMPLETED]
        assert len(completed) == 2

    def test_high_load_heavy_congestion(self):
        """极高负载：大量任务、少量机器"""
        config = SimConfig(num_machines=2, sim_days=1,
                           normal_tasks_per_day=50, priority_tasks_per_day=20,
                           failure_prob_per_machine_per_day=0, seed=42)
        sim = Simulator(config)
        metrics = sim.run()
        # 应该有大量未完成任务
        total_arrived = sum(len(v) for v in sim.task_arrivals.values())
        completed = len(metrics.completed_tasks)
        # 2台机器一天最多完成 1440/30 * 2 ≈ 96 个（假设最短30分钟），但实际任务更多
        assert completed > 0
        assert completed <= total_arrived


# ==================== 边界测试 ====================

class TestSimulatorBoundary:
    def test_one_day_simulation(self):
        config = SimConfig(num_machines=5, sim_days=1, seed=42)
        sim = Simulator(config)
        assert sim.total_minutes == MINUTES_PER_DAY

    def test_machines_count_matches_config(self):
        for n in [1, 5, 50]:
            config = SimConfig(num_machines=n, sim_days=1, seed=1,
                               normal_tasks_per_day=0, priority_tasks_per_day=0,
                               failure_prob_per_machine_per_day=0)
            sim = Simulator(config)
            assert len(sim.machines) == n

    def test_utilization_zero_without_tasks(self):
        config = SimConfig(num_machines=5, sim_days=1,
                           normal_tasks_per_day=0, priority_tasks_per_day=0,
                           failure_prob_per_machine_per_day=0, seed=1)
        sim = Simulator(config)
        metrics = sim.run()
        summary = metrics.summary(sim.total_minutes, config.num_machines)
        assert summary["集群利用率(%)"] == 0.0

    def test_summary_structure(self):
        """summary 返回所有预期的键"""
        config = SimConfig(num_machines=3, sim_days=1, seed=42)
        sim = Simulator(config)
        metrics = sim.run()
        summary = metrics.summary(sim.total_minutes, config.num_machines)
        expected_keys = [
            "总任务到达", "普通任务到达", "优先任务到达",
            "完成任务数", "普通任务完成", "优先任务完成",
            "普通任务平均等待(分钟)", "优先任务平均等待(分钟)",
            "普通任务平均周转(分钟)", "优先任务平均周转(分钟)",
            "机器故障次数", "任务被中断次数",
            "集群利用率(%)",
            "未完成(运行中)", "未完成(等待中)",
        ]
        for key in expected_keys:
            assert key in summary, f"缺少键: {key}"

    def test_step_data_count_matches_simulation_length(self):
        """step_data 条数应等于总模拟分钟数"""
        config = SimConfig(num_machines=3, sim_days=1,
                           normal_tasks_per_day=0, priority_tasks_per_day=0,
                           failure_prob_per_machine_per_day=0, seed=1)
        sim = Simulator(config)
        metrics = sim.run()
        assert len(metrics.step_data) == MINUTES_PER_DAY

    def test_machine_states_sum_to_total(self):
        """每一步：忙碌+维修+空闲 = 总机器数"""
        config = SimConfig(num_machines=5, sim_days=1,
                           failure_prob_per_machine_per_day=0.1, seed=42)
        sim = Simulator(config)
        metrics = sim.run()
        for step in metrics.step_data:
            total = step.busy_machines + step.repairing_machines + step.available_machines
            assert total == 5, (
                f"t={step.time}: busy={step.busy_machines} + "
                f"repair={step.repairing_machines} + "
                f"avail={step.available_machines} = {total} != 5"
            )


class TestMetricsSummary:
    def test_summary_empty(self):
        """空指标的 summary 不应崩溃"""
        m = MetricsCollector()
        s = m.summary(total_minutes=1440, num_machines=5)
        assert s["完成任务数"] == 0
        assert s["集群利用率(%)"] == 0.0
        assert s["普通任务平均等待(分钟)"] == 0
        assert s["优先任务平均等待(分钟)"] == 0

    def test_utilization_calculation(self):
        """利用率手动计算验证"""
        m = MetricsCollector()
        from metrics import StepMetrics
        # 10步，每步5台忙碌
        for i in range(10):
            m.step_data.append(StepMetrics(
                time=i, queue_size=0, priority_queue_size=0,
                busy_machines=5, repairing_machines=0, available_machines=5
            ))
        # utilization = 100 * 50 / (10 * 10) = 50%
        assert m._calc_utilization(total_minutes=10, num_machines=10) == 50.0
