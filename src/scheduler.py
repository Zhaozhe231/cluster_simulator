"""调度策略模块

策略说明：
- FIFO: 先到先服务，优先任务插队到队首
- PRIORITY_FIRST: 始终优先处理优先任务，同类型内按到达时间排序
- SJF (Shortest Job First): 最短任务优先，优先任务仍有更高权重
- ADAPTIVE: 根据拥塞度自动切换上述策略
"""

from enum import Enum
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

from task import Task, TaskType, TaskStatus


class SchedulePolicy(Enum):
    FIFO = "fifo"
    PRIORITY_FIRST = "priority_first"
    SJF = "sjf"
    ADAPTIVE = "adaptive"


# 自适应调度的拥塞阈值
CONGESTION_LOW = 0.5    # 拥塞度 < 0.5 → FIFO（轻负载，简单高效）
CONGESTION_HIGH = 2.0   # 拥塞度 > 2.0 → SJF（重负载，最大化吞吐）
                        # 0.5~2.0 之间 → PRIORITY_FIRST（中等负载，保障优先任务）


class Scheduler:
    def __init__(self, policy: SchedulePolicy = SchedulePolicy.ADAPTIVE):
        self.policy = policy
        self.wait_queue: list[Task] = []
        self._policy_history: list[tuple[int, str]] = []  # (时间, 策略名)
        self._current_effective_policy: SchedulePolicy = policy

    @property
    def queue_size(self) -> int:
        return len(self.wait_queue)

    @property
    def priority_queue_size(self) -> int:
        return sum(1 for t in self.wait_queue if t.is_priority)

    @property
    def normal_queue_size(self) -> int:
        return sum(1 for t in self.wait_queue if not t.is_priority)

    def submit_task(self, task: Task):
        """提交任务到等待队列"""
        task.status = TaskStatus.WAITING
        self.wait_queue.append(task)

    def get_congestion_ratio(self, available_machines: int) -> float:
        """计算拥塞度 = 等待任务数 / 可用机器数"""
        if available_machines <= 0:
            return float('inf') if self.wait_queue else 0.0
        return len(self.wait_queue) / available_machines

    def _resolve_effective_policy(self, available_machines: int, current_time: int) -> SchedulePolicy:
        """自适应模式下根据拥塞度决定实际策略"""
        if self.policy != SchedulePolicy.ADAPTIVE:
            return self.policy

        congestion = self.get_congestion_ratio(available_machines)

        if congestion < CONGESTION_LOW:
            effective = SchedulePolicy.FIFO
        elif congestion > CONGESTION_HIGH:
            effective = SchedulePolicy.SJF
        else:
            effective = SchedulePolicy.PRIORITY_FIRST

        # 记录策略切换
        if effective != self._current_effective_policy:
            self._policy_history.append((current_time, effective.value))
            self._current_effective_policy = effective

        return effective

    def update_adaptive_state(self, available_machines: int, current_time: int):
        """更新自适应策略状态（即使没有空闲机器也要调用）"""
        self._resolve_effective_policy(available_machines, current_time)

    def schedule(self, available_machines: int, current_time: int) -> list[Task]:
        """
        从等待队列中选取任务分配给可用机器。
        返回按调度顺序排列的任务列表（最多 available_machines 个）。
        """
        if not self.wait_queue or available_machines <= 0:
            return []

        effective_policy = self._resolve_effective_policy(available_machines, current_time)

        # 根据策略排序
        if effective_policy == SchedulePolicy.FIFO:
            sorted_tasks = self._sort_fifo()
        elif effective_policy == SchedulePolicy.PRIORITY_FIRST:
            sorted_tasks = self._sort_priority_first()
        elif effective_policy == SchedulePolicy.SJF:
            sorted_tasks = self._sort_sjf()
        else:
            sorted_tasks = self._sort_fifo()

        # 取出要调度的任务
        to_dispatch = sorted_tasks[:available_machines]
        for task in to_dispatch:
            self.wait_queue.remove(task)

        return to_dispatch

    def _sort_fifo(self) -> list[Task]:
        """FIFO：严格按到达时间排序，不区分任务类型"""
        return sorted(self.wait_queue, key=lambda t: t.arrival_time)

    def _sort_priority_first(self) -> list[Task]:
        """优先级优先：优先任务按到达时间排序在前，普通任务按到达时间排序在后"""
        return sorted(
            self.wait_queue,
            key=lambda t: (0 if t.is_priority else 1, t.arrival_time)
        )

    def _sort_sjf(self) -> list[Task]:
        """最短任务优先：优先任务仍有更高权重，同优先级内按剩余时间排序"""
        return sorted(
            self.wait_queue,
            key=lambda t: (0 if t.is_priority else 1, t.remaining_time)
        )

    def get_policy_history(self) -> list[tuple[int, str]]:
        """获取自适应策略切换历史"""
        return list(self._policy_history)
