"""任务模型"""

from enum import Enum
from dataclasses import dataclass, field


class TaskType(Enum):
    NORMAL = "normal"       # 普通任务：每天早上8点批量发布
    PRIORITY = "priority"   # 优先任务：随机时间发布，可插队


class TaskStatus(Enum):
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    PREEMPTED = "preempted"  # 被优先任务抢占


@dataclass
class Task:
    task_id: int
    task_type: TaskType
    duration: int               # 执行时长（分钟）
    arrival_time: int           # 到达时间（模拟分钟数）
    status: TaskStatus = TaskStatus.WAITING
    start_time: int = -1        # 最近一次开始执行时间
    finish_time: int = -1       # 完成时间
    assigned_machine: int = -1  # 分配的机器ID
    remaining_time: int = -1    # 剩余执行时间（用于抢占恢复）
    total_wait_time: int = 0    # 累计等待时间（含被抢占后重新等待）
    _last_queue_time: int = -1  # 上次进入队列的时间（内部追踪）

    def __post_init__(self):
        if self.remaining_time < 0:
            self.remaining_time = self.duration
        self._last_queue_time = self.arrival_time

    @property
    def wait_time(self) -> int:
        """累计等待时间"""
        return self.total_wait_time if self.total_wait_time > 0 else (
            self.start_time - self.arrival_time if self.start_time >= 0 else -1
        )

    @property
    def turnaround_time(self) -> int:
        """周转时间"""
        if self.finish_time >= 0:
            return self.finish_time - self.arrival_time
        return -1

    @property
    def is_priority(self) -> bool:
        return self.task_type == TaskType.PRIORITY
