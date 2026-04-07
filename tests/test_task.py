"""任务模型测试"""

import pytest
from task import Task, TaskType, TaskStatus


# ==================== 正向流程 ====================

class TestTaskNormal:
    def test_create_normal_task(self):
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=480)
        assert t.task_id == 0
        assert t.task_type == TaskType.NORMAL
        assert t.duration == 60
        assert t.remaining_time == 60  # __post_init__ 自动设置
        assert t.status == TaskStatus.WAITING
        assert not t.is_priority

    def test_create_priority_task(self):
        t = Task(task_id=1, task_type=TaskType.PRIORITY, duration=30, arrival_time=100)
        assert t.is_priority
        assert t.remaining_time == 30

    def test_wait_time_after_start(self):
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=100)
        t.start_time = 150
        assert t.wait_time == 50

    def test_turnaround_time(self):
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=100)
        t.start_time = 150
        t.finish_time = 210
        assert t.turnaround_time == 110  # 210 - 100

    def test_total_wait_time_accumulation(self):
        """被抢占后重新调度，累计等待时间应正确"""
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=100, arrival_time=0)
        # 第一次等了 10 分钟后开始执行
        t.total_wait_time = 10
        t.start_time = 10
        # 被抢占，重新入队，又等了 20 分钟
        t.total_wait_time += 20
        t.start_time = 50
        assert t.wait_time == 30  # 累计 10 + 20

    def test_remaining_time_explicit(self):
        """显式指定 remaining_time 不应被覆盖"""
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=100,
                 arrival_time=0, remaining_time=40)
        assert t.remaining_time == 40

    def test_last_queue_time_init(self):
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=200)
        assert t._last_queue_time == 200


# ==================== 异常输入 ====================

class TestTaskAbnormal:
    def test_zero_duration(self):
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=0, arrival_time=0)
        assert t.duration == 0
        assert t.remaining_time == 0

    def test_negative_arrival_time(self):
        """负到达时间不应崩溃（边界输入）"""
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=-10)
        assert t.arrival_time == -10
        assert t._last_queue_time == -10

    def test_wait_time_before_start(self):
        """未开始执行时 wait_time 返回 -1"""
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=0)
        assert t.wait_time == -1

    def test_turnaround_before_finish(self):
        """未完成时 turnaround_time 返回 -1"""
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=0)
        t.start_time = 10
        assert t.turnaround_time == -1

    def test_very_large_duration(self):
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=10**9, arrival_time=0)
        assert t.remaining_time == 10**9


# ==================== 边界测试 ====================

class TestTaskBoundary:
    def test_duration_one_minute(self):
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=1, arrival_time=0)
        assert t.remaining_time == 1

    def test_arrival_at_time_zero(self):
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=0)
        t.start_time = 0
        assert t.wait_time == 0

    def test_same_start_and_arrival(self):
        """到达即执行，等待时间为0"""
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=500)
        t.start_time = 500
        assert t.wait_time == 0

    def test_task_id_zero(self):
        t = Task(task_id=0, task_type=TaskType.NORMAL, duration=60, arrival_time=0)
        assert t.task_id == 0
