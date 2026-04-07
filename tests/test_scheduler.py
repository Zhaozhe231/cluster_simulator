"""调度器测试"""

import pytest
from task import Task, TaskType, TaskStatus
from scheduler import Scheduler, SchedulePolicy, CONGESTION_LOW, CONGESTION_HIGH


def _make_task(tid, ttype=TaskType.NORMAL, duration=60, arrival=0, remaining=None):
    t = Task(task_id=tid, task_type=ttype, duration=duration, arrival_time=arrival)
    if remaining is not None:
        t.remaining_time = remaining
    return t


# ==================== 正向流程 ====================

class TestSchedulerFIFO:
    def test_fifo_strict_arrival_order(self):
        """FIFO 严格按到达时间，不区分类型"""
        s = Scheduler(SchedulePolicy.FIFO)
        t1 = _make_task(1, TaskType.NORMAL, arrival=100)
        t2 = _make_task(2, TaskType.PRIORITY, arrival=200)
        t3 = _make_task(3, TaskType.NORMAL, arrival=50)
        s.submit_task(t1)
        s.submit_task(t2)
        s.submit_task(t3)
        result = s.schedule(available_machines=3, current_time=300)
        assert [t.task_id for t in result] == [3, 1, 2]

    def test_fifo_normal_before_priority_if_earlier(self):
        """FIFO 中普通任务如果到达更早，应排在优先任务前面"""
        s = Scheduler(SchedulePolicy.FIFO)
        normal = _make_task(1, TaskType.NORMAL, arrival=10)
        priority = _make_task(2, TaskType.PRIORITY, arrival=20)
        s.submit_task(normal)
        s.submit_task(priority)
        result = s.schedule(available_machines=1, current_time=30)
        assert result[0].task_id == 1


class TestSchedulerPriorityFirst:
    def test_priority_tasks_first(self):
        """优先任务始终排在普通任务前面"""
        s = Scheduler(SchedulePolicy.PRIORITY_FIRST)
        normal = _make_task(1, TaskType.NORMAL, arrival=0)
        priority = _make_task(2, TaskType.PRIORITY, arrival=100)  # 晚到但优先
        s.submit_task(normal)
        s.submit_task(priority)
        result = s.schedule(available_machines=1, current_time=200)
        assert result[0].task_id == 2

    def test_priority_among_same_type_by_arrival(self):
        """同类型内按到达时间排序"""
        s = Scheduler(SchedulePolicy.PRIORITY_FIRST)
        p1 = _make_task(1, TaskType.PRIORITY, arrival=200)
        p2 = _make_task(2, TaskType.PRIORITY, arrival=100)
        s.submit_task(p1)
        s.submit_task(p2)
        result = s.schedule(available_machines=2, current_time=300)
        assert [t.task_id for t in result] == [2, 1]

    def test_fifo_differs_from_priority_first(self):
        """FIFO 和 PRIORITY_FIRST 对混合任务结果不同"""
        tasks_data = [
            (1, TaskType.NORMAL, 10),
            (2, TaskType.PRIORITY, 50),
        ]
        s_fifo = Scheduler(SchedulePolicy.FIFO)
        s_pf = Scheduler(SchedulePolicy.PRIORITY_FIRST)
        for tid, tt, arr in tasks_data:
            s_fifo.submit_task(_make_task(tid, tt, arrival=arr))
            s_pf.submit_task(_make_task(tid, tt, arrival=arr))

        r_fifo = s_fifo.schedule(1, 100)
        r_pf = s_pf.schedule(1, 100)
        # FIFO 选到达最早的(normal, arrival=10)
        # PRIORITY_FIRST 选优先任务(priority, arrival=50)
        assert r_fifo[0].task_id == 1
        assert r_pf[0].task_id == 2


class TestSchedulerSJF:
    def test_sjf_shortest_first(self):
        """优先级相同时，短任务优先"""
        s = Scheduler(SchedulePolicy.SJF)
        long_task = _make_task(1, TaskType.NORMAL, duration=180, arrival=0)
        short_task = _make_task(2, TaskType.NORMAL, duration=30, arrival=0)
        s.submit_task(long_task)
        s.submit_task(short_task)
        result = s.schedule(available_machines=1, current_time=0)
        assert result[0].task_id == 2

    def test_sjf_priority_still_first(self):
        """SJF 中优先任务仍然优先于更短的普通任务"""
        s = Scheduler(SchedulePolicy.SJF)
        short_normal = _make_task(1, TaskType.NORMAL, duration=10, arrival=0)
        long_priority = _make_task(2, TaskType.PRIORITY, duration=200, arrival=0)
        s.submit_task(short_normal)
        s.submit_task(long_priority)
        result = s.schedule(available_machines=1, current_time=0)
        assert result[0].task_id == 2

    def test_sjf_uses_remaining_time(self):
        """SJF 应按 remaining_time 排序（被抢占后恢复的任务）"""
        s = Scheduler(SchedulePolicy.SJF)
        t1 = _make_task(1, TaskType.NORMAL, duration=100, arrival=0, remaining=10)
        t2 = _make_task(2, TaskType.NORMAL, duration=50, arrival=0)  # remaining=50
        s.submit_task(t1)
        s.submit_task(t2)
        result = s.schedule(available_machines=1, current_time=0)
        assert result[0].task_id == 1  # remaining=10 < 50


class TestSchedulerAdaptive:
    def test_adaptive_low_congestion_uses_fifo(self):
        """低拥塞 → FIFO"""
        s = Scheduler(SchedulePolicy.ADAPTIVE)
        s.submit_task(_make_task(1, arrival=0))
        # 1 task / 10 machines = 0.1 < CONGESTION_LOW
        s.schedule(available_machines=10, current_time=0)
        assert s._current_effective_policy == SchedulePolicy.FIFO

    def test_adaptive_medium_congestion_uses_priority(self):
        """中拥塞 → PRIORITY_FIRST"""
        s = Scheduler(SchedulePolicy.ADAPTIVE)
        for i in range(5):
            s.submit_task(_make_task(i, arrival=i))
        # 5 tasks / 5 machines = 1.0, CONGESTION_LOW < 1.0 < CONGESTION_HIGH
        s.schedule(available_machines=5, current_time=100)
        assert s._current_effective_policy == SchedulePolicy.PRIORITY_FIRST

    def test_adaptive_high_congestion_uses_sjf(self):
        """高拥塞 → SJF"""
        s = Scheduler(SchedulePolicy.ADAPTIVE)
        for i in range(30):
            s.submit_task(_make_task(i, arrival=i))
        # 30 tasks / 10 machines = 3.0 > CONGESTION_HIGH
        s.schedule(available_machines=10, current_time=100)
        assert s._current_effective_policy == SchedulePolicy.SJF

    def test_adaptive_records_policy_switch(self):
        """策略切换应被记录"""
        s = Scheduler(SchedulePolicy.ADAPTIVE)
        # 先触发一次低拥塞
        s.submit_task(_make_task(0))
        s.schedule(available_machines=10, current_time=0)
        # 再加大拥塞
        for i in range(30):
            s.submit_task(_make_task(i + 1, arrival=0))
        s.schedule(available_machines=10, current_time=100)

        history = s.get_policy_history()
        assert len(history) >= 2
        policies = [p for _, p in history]
        assert "fifo" in policies
        assert "sjf" in policies

    def test_update_adaptive_state_no_machines(self):
        """0台可用机器时应切换到 SJF（无穷拥塞）"""
        s = Scheduler(SchedulePolicy.ADAPTIVE)
        s.submit_task(_make_task(0))
        s.update_adaptive_state(available_machines=0, current_time=0)
        assert s._current_effective_policy == SchedulePolicy.SJF


class TestSchedulerGeneral:
    def test_submit_sets_waiting(self):
        s = Scheduler()
        t = _make_task(0)
        t.status = TaskStatus.COMPLETED
        s.submit_task(t)
        assert t.status == TaskStatus.WAITING

    def test_schedule_removes_from_queue(self):
        s = Scheduler(SchedulePolicy.FIFO)
        s.submit_task(_make_task(1, arrival=0))
        s.submit_task(_make_task(2, arrival=0))
        result = s.schedule(available_machines=1, current_time=0)
        assert len(result) == 1
        assert s.queue_size == 1

    def test_schedule_respects_machine_limit(self):
        """调度数量不超过可用机器数"""
        s = Scheduler(SchedulePolicy.FIFO)
        for i in range(10):
            s.submit_task(_make_task(i, arrival=0))
        result = s.schedule(available_machines=3, current_time=0)
        assert len(result) == 3
        assert s.queue_size == 7

    def test_queue_size_properties(self):
        s = Scheduler()
        s.submit_task(_make_task(1, TaskType.NORMAL))
        s.submit_task(_make_task(2, TaskType.PRIORITY))
        s.submit_task(_make_task(3, TaskType.NORMAL))
        assert s.queue_size == 3
        assert s.priority_queue_size == 1
        assert s.normal_queue_size == 2


# ==================== 异常输入 ====================

class TestSchedulerAbnormal:
    def test_schedule_empty_queue(self):
        s = Scheduler(SchedulePolicy.FIFO)
        result = s.schedule(available_machines=5, current_time=0)
        assert result == []

    def test_schedule_zero_machines(self):
        s = Scheduler(SchedulePolicy.FIFO)
        s.submit_task(_make_task(1))
        result = s.schedule(available_machines=0, current_time=0)
        assert result == []
        assert s.queue_size == 1  # 任务仍在队列中

    def test_schedule_negative_machines(self):
        s = Scheduler(SchedulePolicy.FIFO)
        s.submit_task(_make_task(1))
        result = s.schedule(available_machines=-1, current_time=0)
        assert result == []

    def test_congestion_ratio_zero_machines_with_tasks(self):
        s = Scheduler()
        s.submit_task(_make_task(1))
        ratio = s.get_congestion_ratio(0)
        assert ratio == float('inf')

    def test_congestion_ratio_zero_machines_empty_queue(self):
        s = Scheduler()
        ratio = s.get_congestion_ratio(0)
        assert ratio == 0.0

    def test_congestion_ratio_negative_machines(self):
        s = Scheduler()
        s.submit_task(_make_task(1))
        ratio = s.get_congestion_ratio(-5)
        assert ratio == float('inf')


# ==================== 边界测试 ====================

class TestSchedulerBoundary:
    def test_single_task_single_machine(self):
        s = Scheduler(SchedulePolicy.FIFO)
        s.submit_task(_make_task(1))
        result = s.schedule(available_machines=1, current_time=0)
        assert len(result) == 1
        assert s.queue_size == 0

    def test_more_machines_than_tasks(self):
        """机器数 > 任务数：所有任务都被调度"""
        s = Scheduler(SchedulePolicy.FIFO)
        s.submit_task(_make_task(1, arrival=0))
        s.submit_task(_make_task(2, arrival=0))
        result = s.schedule(available_machines=10, current_time=0)
        assert len(result) == 2
        assert s.queue_size == 0

    def test_exact_congestion_low_threshold(self):
        """拥塞度恰好等于 CONGESTION_LOW 时应选 PRIORITY_FIRST"""
        s = Scheduler(SchedulePolicy.ADAPTIVE)
        # congestion = 1 task / 2 machines = 0.5 = CONGESTION_LOW
        s.submit_task(_make_task(0))
        s.schedule(available_machines=2, current_time=0)
        # 0.5 不 < 0.5，也不 > 2.0，所以是 PRIORITY_FIRST
        assert s._current_effective_policy == SchedulePolicy.PRIORITY_FIRST

    def test_exact_congestion_high_threshold(self):
        """拥塞度恰好等于 CONGESTION_HIGH 时应选 PRIORITY_FIRST"""
        s = Scheduler(SchedulePolicy.ADAPTIVE)
        for i in range(10):
            s.submit_task(_make_task(i))
        # congestion = 10 / 5 = 2.0 = CONGESTION_HIGH
        s.schedule(available_machines=5, current_time=0)
        # 2.0 不 < 0.5，也不 > 2.0，所以是 PRIORITY_FIRST
        assert s._current_effective_policy == SchedulePolicy.PRIORITY_FIRST

    def test_all_same_arrival_time(self):
        """所有任务同时到达"""
        s = Scheduler(SchedulePolicy.FIFO)
        for i in range(5):
            s.submit_task(_make_task(i, arrival=100))
        result = s.schedule(available_machines=5, current_time=100)
        assert len(result) == 5

    def test_non_adaptive_ignores_congestion(self):
        """非自适应模式下拥塞度不影响策略"""
        s = Scheduler(SchedulePolicy.FIFO)
        for i in range(100):
            s.submit_task(_make_task(i))
        s.schedule(available_machines=1, current_time=0)
        assert s._current_effective_policy == SchedulePolicy.FIFO
        assert s.get_policy_history() == []
