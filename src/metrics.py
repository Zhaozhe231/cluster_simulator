"""指标收集与可视化"""

from dataclasses import dataclass, field
from task import Task, TaskType


@dataclass
class StepMetrics:
    time: int
    queue_size: int
    priority_queue_size: int
    busy_machines: int
    repairing_machines: int
    available_machines: int


class MetricsCollector:
    def __init__(self):
        self.step_data: list[StepMetrics] = []
        self.completed_tasks: list[Task] = []
        self.events: list[dict] = []
        self._arrived_normal = 0
        self._arrived_priority = 0
        self.unfinished_running = 0
        self.unfinished_waiting = 0

    def record_step(self, **kwargs):
        self.step_data.append(StepMetrics(**kwargs))

    def record_task_arrived(self, task: Task, time: int):
        if task.is_priority:
            self._arrived_priority += 1
        else:
            self._arrived_normal += 1

    def record_task_started(self, task: Task, time: int):
        pass

    def record_task_completed(self, task: Task, time: int):
        self.completed_tasks.append(task)

    def record_event(self, event_type: str, time: int, **kwargs):
        self.events.append({"type": event_type, "time": time, **kwargs})

    # ---- 汇总统计 ----

    def summary(self, total_minutes: int, num_machines: int) -> dict:
        completed = self.completed_tasks
        normal_completed = [t for t in completed if not t.is_priority]
        priority_completed = [t for t in completed if t.is_priority]

        def avg(lst):
            return sum(lst) / len(lst) if lst else 0

        normal_wait = [t.wait_time for t in normal_completed if t.wait_time >= 0]
        priority_wait = [t.wait_time for t in priority_completed if t.wait_time >= 0]
        normal_turn = [t.turnaround_time for t in normal_completed if t.turnaround_time >= 0]
        priority_turn = [t.turnaround_time for t in priority_completed if t.turnaround_time >= 0]

        failures = [e for e in self.events if e["type"] == "machine_failed"]
        preemptions = [e for e in self.events if e["type"] == "task_preempted"]

        return {
            "总任务到达": self._arrived_normal + self._arrived_priority,
            "普通任务到达": self._arrived_normal,
            "优先任务到达": self._arrived_priority,
            "完成任务数": len(completed),
            "普通任务完成": len(normal_completed),
            "优先任务完成": len(priority_completed),
            "普通任务平均等待(分钟)": round(avg(normal_wait), 1),
            "优先任务平均等待(分钟)": round(avg(priority_wait), 1),
            "普通任务平均周转(分钟)": round(avg(normal_turn), 1),
            "优先任务平均周转(分钟)": round(avg(priority_turn), 1),
            "机器故障次数": len(failures),
            "任务被中断次数": len(preemptions),
            "集群利用率(%)": self._calc_utilization(total_minutes, num_machines),
            "未完成(运行中)": self.unfinished_running,
            "未完成(等待中)": self.unfinished_waiting,
        }

    def _calc_utilization(self, total_minutes: int, num_machines: int) -> float:
        if not self.step_data:
            return 0.0
        total_busy = sum(s.busy_machines for s in self.step_data)
        return round(100 * total_busy / (total_minutes * num_machines), 1)

    # ---- 可视化 ----

    def plot(self, total_minutes: int, num_machines: int, save_path: str = "simulation_results.png"):
        """生成模拟结果图表"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.font_manager as fm
        except ImportError:
            print("matplotlib 未安装，跳过图表生成。安装: pip install matplotlib")
            return

        # 设置中文字体（Windows）
        import pathlib
        font_path = None
        for candidate in ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
                          'C:/Windows/Fonts/simsun.ttc']:
            if pathlib.Path(candidate).exists():
                font_path = candidate
                break
        if font_path:
            font_prop = fm.FontProperties(fname=font_path)
            plt.rcParams['font.family'] = font_prop.get_name()
        else:
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        # 每小时采样一次以减少数据点
        sample_interval = 60
        times_h = [s.time / 60 for s in self.step_data[::sample_interval]]  # 转换为小时
        queue = [s.queue_size for s in self.step_data[::sample_interval]]
        pqueue = [s.priority_queue_size for s in self.step_data[::sample_interval]]
        busy = [s.busy_machines for s in self.step_data[::sample_interval]]
        repairing = [s.repairing_machines for s in self.step_data[::sample_interval]]
        avail = [s.available_machines for s in self.step_data[::sample_interval]]

        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle("集群调度模拟结果", fontsize=16, fontweight='bold')

        # 图1: 队列长度
        ax = axes[0][0]
        ax.plot(times_h, queue, label='总队列', color='steelblue', linewidth=0.8)
        ax.plot(times_h, pqueue, label='优先队列', color='crimson', linewidth=0.8)
        ax.set_title("任务队列长度")
        ax.set_xlabel("时间 (小时)")
        ax.set_ylabel("任务数")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 图2: 机器状态
        ax = axes[0][1]
        ax.stackplot(times_h, busy, repairing, avail,
                     labels=['忙碌', '维修', '空闲'],
                     colors=['#ff7f0e', '#d62728', '#2ca02c'], alpha=0.8)
        ax.set_title("机器状态分布")
        ax.set_xlabel("时间 (小时)")
        ax.set_ylabel("机器数")
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)

        # 图3: 任务完成时间分布
        ax = axes[1][0]
        normal_wait = [t.wait_time for t in self.completed_tasks
                       if not t.is_priority and t.wait_time >= 0]
        priority_wait = [t.wait_time for t in self.completed_tasks
                         if t.is_priority and t.wait_time >= 0]
        if normal_wait:
            ax.hist(normal_wait, bins=30, alpha=0.7, label='普通任务', color='steelblue')
        if priority_wait:
            ax.hist(priority_wait, bins=30, alpha=0.7, label='优先任务', color='crimson')
        ax.set_title("任务等待时间分布")
        ax.set_xlabel("等待时间 (分钟)")
        ax.set_ylabel("任务数")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 图4: 统计摘要文本
        ax = axes[1][1]
        ax.axis('off')
        summary = self.summary(total_minutes, num_machines)
        text_lines = []
        for k, v in summary.items():
            text_lines.append(f"{k}: {v}")
        ax.text(0.1, 0.95, "\n".join(text_lines),
                transform=ax.transAxes, fontsize=11,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        ax.set_title("统计摘要")

        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"图表已保存到: {save_path}")
        plt.close()
