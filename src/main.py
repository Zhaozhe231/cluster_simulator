"""集群调度模拟器 - 主入口

用法:
    python main.py                          # 使用默认参数运行自适应策略
    python main.py --machines 20 --days 14  # 自定义参数
    python main.py --compare                # 对比所有策略
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulator import Simulator, SimConfig
from scheduler import SchedulePolicy


def run_single(config: SimConfig):
    """运行单次模拟"""
    sim = Simulator(config)
    metrics = sim.run()

    # 打印统计摘要
    summary = metrics.summary(sim.total_minutes, config.num_machines)
    print("\n===== 统计摘要 =====")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # 打印自适应策略切换历史
    if config.schedule_policy == SchedulePolicy.ADAPTIVE:
        history = sim.scheduler.get_policy_history()
        if history:
            print(f"\n===== 自适应策略切换 (共{len(history)}次) =====")
            for time, policy in history[:20]:  # 最多显示20条
                day = time // (24 * 60)
                hour = (time % (24 * 60)) // 60
                minute = time % 60
                print(f"  第{day}天 {hour:02d}:{minute:02d} → {policy}")
            if len(history) > 20:
                print(f"  ... 还有 {len(history) - 20} 次切换")

    # 生成图表
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               f"result_{config.schedule_policy.value}.png")
    metrics.plot(sim.total_minutes, config.num_machines, save_path=output_file)


def run_compare(base_config: SimConfig):
    """对比所有调度策略"""
    policies = [
        SchedulePolicy.FIFO,
        SchedulePolicy.PRIORITY_FIRST,
        SchedulePolicy.SJF,
        SchedulePolicy.ADAPTIVE,
    ]

    results = {}
    for policy in policies:
        print(f"\n{'=' * 60}")
        print(f"策略: {policy.value}")
        print(f"{'=' * 60}")

        config = SimConfig(
            num_machines=base_config.num_machines,
            sim_days=base_config.sim_days,
            normal_tasks_per_day=base_config.normal_tasks_per_day,
            normal_duration_range=base_config.normal_duration_range,
            priority_tasks_per_day=base_config.priority_tasks_per_day,
            priority_duration_range=base_config.priority_duration_range,
            failure_prob_per_machine_per_day=base_config.failure_prob_per_machine_per_day,
            schedule_policy=policy,
            seed=base_config.seed,
        )

        sim = Simulator(config)
        metrics = sim.run()
        summary = metrics.summary(sim.total_minutes, config.num_machines)
        results[policy.value] = summary

        output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   f"result_{policy.value}.png")
        metrics.plot(sim.total_minutes, config.num_machines, save_path=output_file)

    # 打印对比表
    print(f"\n{'=' * 80}")
    print("策略对比总结")
    print(f"{'=' * 80}")

    header = f"{'指标':<28s}"
    for p in policies:
        header += f"{p.value:>12s}"
    print(header)
    print("-" * 80)

    keys = list(results[policies[0].value].keys())
    for key in keys:
        row = f"{key:<26s}"
        for p in policies:
            val = results[p.value][key]
            row += f"{str(val):>12s}"
        print(row)


def main():
    parser = argparse.ArgumentParser(description="集群调度模拟器")
    parser.add_argument("--machines", type=int, default=10, help="机器数量 (默认10)")
    parser.add_argument("--days", type=int, default=7, help="模拟天数 (默认7)")
    parser.add_argument("--normal-tasks", type=int, default=15, help="每天普通任务数 (默认15)")
    parser.add_argument("--priority-tasks", type=float, default=5, help="每天平均优先任务数 (默认5)")
    parser.add_argument("--failure-rate", type=float, default=0.03,
                        help="每台机器每天故障概率 (默认0.03)")
    parser.add_argument("--policy", type=str, default="adaptive",
                        choices=["fifo", "priority_first", "sjf", "adaptive"],
                        help="调度策略 (默认adaptive)")
    parser.add_argument("--compare", action="store_true", help="对比所有策略")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认42)")

    args = parser.parse_args()

    config = SimConfig(
        num_machines=args.machines,
        sim_days=args.days,
        normal_tasks_per_day=args.normal_tasks,
        priority_tasks_per_day=args.priority_tasks,
        failure_prob_per_machine_per_day=args.failure_rate,
        schedule_policy=SchedulePolicy(args.policy),
        seed=args.seed,
    )

    if args.compare:
        run_compare(config)
    else:
        run_single(config)


if __name__ == "__main__":
    main()
