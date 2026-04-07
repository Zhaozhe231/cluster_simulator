"""离散事件模拟引擎

模拟流程（按分钟步进）：
1. 检查机器维修完成
2. 检查任务完成
3. 检查机器故障
4. 生成新任务（普通任务8:00批量 / 优先任务随机）
5. 调度等待队列中的任务
6. 收集指标
"""

import random
from dataclasses import dataclass, field

from task import Task, TaskType, TaskStatus
from machine import Machine, MachineState
from scheduler import Scheduler, SchedulePolicy
from metrics import MetricsCollector


@dataclass
class SimConfig:
    num_machines: int = 10              # 机器数量
    sim_days: int = 7                   # 模拟天数
    # 普通任务参数
    normal_tasks_per_day: int = 15      # 每天8点发布的普通任务数
    normal_duration_range: tuple = (30, 180)  # 普通任务执行时长范围（分钟）
    # 优先任务参数
    priority_tasks_per_day: float = 5   # 每天平均优先任务数
    priority_duration_range: tuple = (15, 120)  # 优先任务执行时长范围
    # 机器故障参数
    failure_prob_per_machine_per_day: float = 0.03  # 每台机器每天故障概率
    # 调度策略
    schedule_policy: SchedulePolicy = SchedulePolicy.ADAPTIVE
    # 随机种子
    seed: int = 42


MINUTES_PER_DAY = 24 * 60
MORNING_8AM = 8 * 60  # 480分钟


class Simulator:
    def __init__(self, config: SimConfig):
        self.config = config
        self.rng = random.Random(config.seed)
        self.current_time = 0
        self.total_minutes = config.sim_days * MINUTES_PER_DAY
        self.next_task_id = 0

        # 初始化机器
        self.machines = [Machine(machine_id=i) for i in range(config.num_machines)]

        # 初始化调度器
        self.scheduler = Scheduler(policy=config.schedule_policy)

        # 指标收集
        self.metrics = MetricsCollector()

        # 所有任务记录
        self.all_tasks: dict[int, Task] = {}

        # 预生成事件
        self._generate_all_events()

    def _new_task_id(self) -> int:
        tid = self.next_task_id
        self.next_task_id += 1
        return tid

    def _generate_all_events(self):
        """预生成所有任务到达事件和机器故障事件"""
        self.task_arrivals: dict[int, list[Task]] = {}  # minute -> [tasks]
        self.failure_events: dict[int, list[int]] = {}   # minute -> [machine_ids]

        for day in range(self.config.sim_days):
            day_start = day * MINUTES_PER_DAY

            # 普通任务：每天8:00批量到达
            arrival_time = day_start + MORNING_8AM
            for _ in range(self.config.normal_tasks_per_day):
                duration = self.rng.randint(*self.config.normal_duration_range)
                task = Task(
                    task_id=self._new_task_id(),
                    task_type=TaskType.NORMAL,
                    duration=duration,
                    arrival_time=arrival_time,
                )
                self.task_arrivals.setdefault(arrival_time, []).append(task)

            # 优先任务：泊松过程近似，随机分布在全天
            num_priority = self.rng.poisson_approx(self.config.priority_tasks_per_day)
            for _ in range(num_priority):
                minute_offset = self.rng.randint(0, MINUTES_PER_DAY - 1)
                arrival_time = day_start + minute_offset
                duration = self.rng.randint(*self.config.priority_duration_range)
                task = Task(
                    task_id=self._new_task_id(),
                    task_type=TaskType.PRIORITY,
                    duration=duration,
                    arrival_time=arrival_time,
                )
                self.task_arrivals.setdefault(arrival_time, []).append(task)

            # 机器故障事件：每台机器每天有一定概率故障
            failure_prob_per_minute = self.config.failure_prob_per_machine_per_day / MINUTES_PER_DAY
            for m in range(self.config.num_machines):
                for minute in range(MINUTES_PER_DAY):
                    if self.rng.random() < failure_prob_per_minute:
                        t = day_start + minute
                        self.failure_events.setdefault(t, []).append(m)

        # 记录总任务数
        total = sum(len(tasks) for tasks in self.task_arrivals.values())
        print(f"预生成 {total} 个任务, {sum(len(v) for v in self.failure_events.values())} 个故障事件")

    def run(self):
        """运行模拟"""
        print(f"开始模拟: {self.config.num_machines} 台机器, "
              f"{self.config.sim_days} 天, 策略={self.config.schedule_policy.value}")
        print("-" * 60)

        for t in range(self.total_minutes):
            self.current_time = t
            self._step_repair_check()
            self._step_task_completion()
            self._step_failure_check()
            self._step_task_arrival()
            self._step_schedule()
            self._step_collect_metrics()

            # 每天打印一次进度
            if t > 0 and t % MINUTES_PER_DAY == 0:
                day = t // MINUTES_PER_DAY
                completed = sum(1 for task in self.all_tasks.values()
                                if task.status == TaskStatus.COMPLETED)
                avail = sum(1 for m in self.machines if m.is_available)
                print(f"  第{day}天结束: 已完成{completed}个任务, "
                      f"队列中{self.scheduler.queue_size}个, "
                      f"可用机器{avail}/{self.config.num_machines}")

        # 统计未完成任务
        unfinished_running = sum(1 for t in self.all_tasks.values()
                                 if t.status == TaskStatus.RUNNING)
        unfinished_waiting = self.scheduler.queue_size
        if unfinished_running + unfinished_waiting > 0:
            print(f"  未完成: {unfinished_running}个运行中, {unfinished_waiting}个等待中")

        print("-" * 60)
        print("模拟完成!")
        self.metrics.unfinished_running = unfinished_running
        self.metrics.unfinished_waiting = unfinished_waiting
        return self.metrics

    def _step_repair_check(self):
        """检查机器维修是否完成"""
        for machine in self.machines:
            if machine.check_repair(self.current_time):
                self.metrics.record_event("machine_repaired", self.current_time,
                                          machine_id=machine.machine_id)

    def _step_task_completion(self):
        """检查正在执行的任务是否完成"""
        for machine in self.machines:
            if (machine.state == MachineState.BUSY and
                    self.current_time >= machine.task_finish_time):
                task = self.all_tasks[machine.current_task_id]
                task.status = TaskStatus.COMPLETED
                task.finish_time = self.current_time
                task.remaining_time = 0
                machine.complete_task()
                self.metrics.record_task_completed(task, self.current_time)

    def _step_failure_check(self):
        """检查机器是否故障"""
        if self.current_time not in self.failure_events:
            return

        for machine_id in self.failure_events[self.current_time]:
            machine = self.machines[machine_id]
            # 已经在维修中的机器不会再次故障
            if machine.state == MachineState.REPAIRING:
                continue

            interrupted_task_id = machine.fail(self.current_time)
            self.metrics.record_event("machine_failed", self.current_time,
                                      machine_id=machine_id)

            # 如果机器上有正在执行的任务，将其放回队列
            if interrupted_task_id >= 0:
                task = self.all_tasks[interrupted_task_id]
                # 计算已执行时间
                elapsed = self.current_time - task.start_time
                task.remaining_time = max(1, task.remaining_time - elapsed)
                task.total_wait_time += task.start_time - task._last_queue_time
                task.status = TaskStatus.PREEMPTED
                task.start_time = -1
                task.assigned_machine = -1
                task._last_queue_time = self.current_time
                self.scheduler.submit_task(task)
                self.metrics.record_event("task_preempted", self.current_time,
                                          task_id=task.task_id)

    def _step_task_arrival(self):
        """处理新到达的任务"""
        if self.current_time not in self.task_arrivals:
            return

        for task in self.task_arrivals[self.current_time]:
            self.all_tasks[task.task_id] = task
            self.scheduler.submit_task(task)
            self.metrics.record_task_arrived(task, self.current_time)

    def _step_schedule(self):
        """调度任务到空闲机器"""
        available = [m for m in self.machines if m.is_available]
        num_available = len(available)

        # 即使没有空闲机器，也要更新自适应策略状态
        self.scheduler.update_adaptive_state(num_available, self.current_time)

        if not available:
            return

        tasks_to_dispatch = self.scheduler.schedule(
            available_machines=num_available,
            current_time=self.current_time
        )

        for task, machine in zip(tasks_to_dispatch, available):
            # 累计等待时间
            task.total_wait_time += self.current_time - task._last_queue_time
            task.status = TaskStatus.RUNNING
            task.start_time = self.current_time
            task.assigned_machine = machine.machine_id
            finish_time = self.current_time + task.remaining_time
            machine.assign_task(task.task_id, finish_time)
            self.metrics.record_task_started(task, self.current_time)

    def _step_collect_metrics(self):
        """每步收集指标"""
        for machine in self.machines:
            machine.update_stats(1)

        self.metrics.record_step(
            time=self.current_time,
            queue_size=self.scheduler.queue_size,
            priority_queue_size=self.scheduler.priority_queue_size,
            busy_machines=sum(1 for m in self.machines if m.state == MachineState.BUSY),
            repairing_machines=sum(1 for m in self.machines if m.state == MachineState.REPAIRING),
            available_machines=sum(1 for m in self.machines if m.is_available),
        )


# 给random.Random加一个泊松近似方法
def _poisson_approx(self, lam):
    """简单泊松随机数生成（Knuth算法）"""
    import math
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= self.random()
        if p < L:
            return k - 1

random.Random.poisson_approx = _poisson_approx
