"""机器模型"""

from enum import Enum
from dataclasses import dataclass


class MachineState(Enum):
    IDLE = "idle"           # 空闲
    BUSY = "busy"           # 正在执行任务
    REPAIRING = "repairing" # 维修中（24小时）


REPAIR_DURATION = 24 * 60  # 24小时 = 1440分钟


@dataclass
class Machine:
    machine_id: int
    state: MachineState = MachineState.IDLE
    current_task_id: int = -1       # 当前执行的任务ID
    task_finish_time: int = -1      # 任务完成时间
    repair_finish_time: int = -1    # 维修完成时间
    total_busy_time: int = 0        # 累计忙碌时间
    total_repair_time: int = 0      # 累计维修时间
    failure_count: int = 0          # 故障次数

    @property
    def is_available(self) -> bool:
        return self.state == MachineState.IDLE

    def assign_task(self, task_id: int, finish_time: int):
        """分配任务"""
        self.state = MachineState.BUSY
        self.current_task_id = task_id
        self.task_finish_time = finish_time

    def complete_task(self):
        """完成任务"""
        self.state = MachineState.IDLE
        self.current_task_id = -1
        self.task_finish_time = -1

    def fail(self, current_time: int):
        """机器故障"""
        self.state = MachineState.REPAIRING
        self.repair_finish_time = current_time + REPAIR_DURATION
        self.failure_count += 1
        prev_task = self.current_task_id
        self.current_task_id = -1
        self.task_finish_time = -1
        return prev_task  # 返回被中断的任务ID

    def check_repair(self, current_time: int) -> bool:
        """检查维修是否完成"""
        if self.state == MachineState.REPAIRING and current_time >= self.repair_finish_time:
            self.state = MachineState.IDLE
            self.repair_finish_time = -1
            return True
        return False

    def update_stats(self, duration: int):
        """更新统计（每步调用）"""
        if self.state == MachineState.BUSY:
            self.total_busy_time += duration
        elif self.state == MachineState.REPAIRING:
            self.total_repair_time += duration
