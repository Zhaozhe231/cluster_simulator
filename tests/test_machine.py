"""机器模型测试"""

import pytest
from machine import Machine, MachineState, REPAIR_DURATION


# ==================== 正向流程 ====================

class TestMachineNormal:
    def test_initial_state(self):
        m = Machine(machine_id=0)
        assert m.state == MachineState.IDLE
        assert m.is_available
        assert m.current_task_id == -1
        assert m.failure_count == 0

    def test_assign_task(self):
        m = Machine(machine_id=0)
        m.assign_task(task_id=5, finish_time=100)
        assert m.state == MachineState.BUSY
        assert not m.is_available
        assert m.current_task_id == 5
        assert m.task_finish_time == 100

    def test_complete_task(self):
        m = Machine(machine_id=0)
        m.assign_task(task_id=5, finish_time=100)
        m.complete_task()
        assert m.state == MachineState.IDLE
        assert m.is_available
        assert m.current_task_id == -1

    def test_fail_idle_machine(self):
        m = Machine(machine_id=0)
        prev = m.fail(current_time=500)
        assert prev == -1  # 没有中断的任务
        assert m.state == MachineState.REPAIRING
        assert m.repair_finish_time == 500 + REPAIR_DURATION
        assert m.failure_count == 1

    def test_fail_busy_machine(self):
        m = Machine(machine_id=0)
        m.assign_task(task_id=7, finish_time=600)
        prev = m.fail(current_time=500)
        assert prev == 7  # 返回被中断的任务
        assert m.state == MachineState.REPAIRING
        assert m.current_task_id == -1

    def test_repair_completes(self):
        m = Machine(machine_id=0)
        m.fail(current_time=0)
        # 在维修完成前
        assert not m.check_repair(REPAIR_DURATION - 1)
        assert m.state == MachineState.REPAIRING
        # 在维修完成时
        assert m.check_repair(REPAIR_DURATION)
        assert m.state == MachineState.IDLE
        assert m.is_available

    def test_repair_duration_24h(self):
        """维修时间应严格为24小时=1440分钟"""
        assert REPAIR_DURATION == 24 * 60
        m = Machine(machine_id=0)
        m.fail(current_time=100)
        assert m.repair_finish_time == 100 + 1440

    def test_update_stats_busy(self):
        m = Machine(machine_id=0)
        m.assign_task(task_id=1, finish_time=100)
        m.update_stats(5)
        assert m.total_busy_time == 5
        m.update_stats(3)
        assert m.total_busy_time == 8

    def test_update_stats_repairing(self):
        m = Machine(machine_id=0)
        m.fail(current_time=0)
        m.update_stats(10)
        assert m.total_repair_time == 10

    def test_update_stats_idle(self):
        m = Machine(machine_id=0)
        m.update_stats(10)
        assert m.total_busy_time == 0
        assert m.total_repair_time == 0

    def test_multiple_failures(self):
        m = Machine(machine_id=0)
        m.fail(current_time=0)
        m.check_repair(REPAIR_DURATION)
        m.fail(current_time=REPAIR_DURATION + 100)
        assert m.failure_count == 2

    def test_full_lifecycle(self):
        """完整生命周期：空闲→忙碌→完成→故障→维修→空闲"""
        m = Machine(machine_id=0)
        assert m.is_available
        m.assign_task(1, 100)
        assert m.state == MachineState.BUSY
        m.complete_task()
        assert m.is_available
        m.fail(200)
        assert m.state == MachineState.REPAIRING
        m.check_repair(200 + REPAIR_DURATION)
        assert m.is_available


# ==================== 异常输入 ====================

class TestMachineAbnormal:
    def test_complete_without_assign(self):
        """未分配任务就调用 complete_task 不应崩溃"""
        m = Machine(machine_id=0)
        m.complete_task()  # 不应抛异常
        assert m.state == MachineState.IDLE

    def test_double_assign(self):
        """连续分配两个任务，第二个覆盖第一个"""
        m = Machine(machine_id=0)
        m.assign_task(1, 100)
        m.assign_task(2, 200)
        assert m.current_task_id == 2
        assert m.task_finish_time == 200

    def test_fail_during_repair(self):
        """维修中的机器再次 fail，应累加 failure_count"""
        m = Machine(machine_id=0)
        m.fail(current_time=0)
        m.fail(current_time=100)  # 再次故障
        assert m.failure_count == 2
        # 维修时间应重置为从第二次故障开始
        assert m.repair_finish_time == 100 + REPAIR_DURATION

    def test_check_repair_on_idle(self):
        """对空闲机器调用 check_repair 应返回 False"""
        m = Machine(machine_id=0)
        assert not m.check_repair(9999)

    def test_check_repair_on_busy(self):
        """对忙碌机器调用 check_repair 应返回 False"""
        m = Machine(machine_id=0)
        m.assign_task(1, 100)
        assert not m.check_repair(9999)


# ==================== 边界测试 ====================

class TestMachineBoundary:
    def test_fail_at_time_zero(self):
        m = Machine(machine_id=0)
        m.fail(current_time=0)
        assert m.repair_finish_time == REPAIR_DURATION

    def test_repair_exactly_at_deadline(self):
        m = Machine(machine_id=0)
        m.fail(current_time=0)
        assert m.check_repair(REPAIR_DURATION)  # 刚好到时间

    def test_repair_one_minute_early(self):
        m = Machine(machine_id=0)
        m.fail(current_time=0)
        assert not m.check_repair(REPAIR_DURATION - 1)  # 差1分钟

    def test_task_finish_at_zero(self):
        m = Machine(machine_id=0)
        m.assign_task(task_id=0, finish_time=0)
        assert m.task_finish_time == 0

    def test_large_machine_id(self):
        m = Machine(machine_id=999999)
        assert m.machine_id == 999999
        m.fail(0)
        assert m.failure_count == 1
