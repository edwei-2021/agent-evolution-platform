#!/usr/bin/env python3
"""Run M acceptance or explicitly scoped tests with optional numbered start menus."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from platform_m.gates import Gates, plans, execute
from scripts.check_start_selection import SelectionCancelled, release_plan, select_start, step_label


def main(argv=None, *, root=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['acceptance','components'], default='acceptance')
    interaction = parser.add_mutually_exclusive_group()
    interaction.add_argument('--interactive', action='store_true', help='Show numbered start menus, including with redirected input')
    interaction.add_argument('--non-interactive', action='store_true', help='Never ask for input (CI/setup)')
    parser.add_argument('--from-stage', choices=[f'M{i}' for i in range(1,8)])
    parser.add_argument('--from-step', type=int, help='Original 1-based step within the selected M stage')
    parser.add_argument('--release-step', help='Source-owned M7 release step ID, e.g. python-gepa_test')
    parser.add_argument('--from-case', help='First fully qualified case in the selected release module')
    parser.add_argument('--list-steps', action='store_true', help='List stages and numbered steps without running tests')
    parser.add_argument('--dry-run', action='store_true', help='Print selected plan and scope without running tests')
    args = parser.parse_args(argv)
    root = Path(root or Path(__file__).resolve().parents[1])
    explicit = any(value is not None for value in (args.from_stage,args.from_step,args.release_step,args.from_case))
    if args.profile == 'components':
        if explicit or args.interactive or args.list_steps or args.dry_run:
            parser.error('Start selection applies to --profile acceptance')
        code, output = execute([sys.executable,'-m','pytest','-s','tests_m','-q'], root, os.environ,
                               interactive=not args.non_interactive)
        print(output)
        print('COMPONENT CHECK ONLY: Docker and actual SDK/production integration are not certified.')
        return code
    if args.from_step is not None and args.from_stage is None:
        parser.error('--from-step requires --from-stage')
    full_plan = plans(root, sys.executable)
    if args.list_steps:
        for stage, commands in full_plan:
            print(stage)
            for index, command in enumerate(commands):
                print(f'  {index+1}. {step_label(stage,index,command)}')
        return 0
    catalog = release_plan(root, str(root/'.venv-nanobot/bin/python'), full_plan[-1][1][-1][0])
    interactive = args.interactive or (sys.stdin.isatty() and not args.non_interactive and not explicit)
    try:
        plan, scope = select_start(full_plan, root, catalog, stage=args.from_stage, step=args.from_step,
                                   release=args.release_step, case=args.from_case, interactive=interactive)
    except SelectionCancelled:
        print('已取消，未執行測試。')
        return 130
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    summary = {key:scope[key] for key in ('startStage','startStep','releaseStep','fromCase','fullMAcceptance')}
    summary.update(omittedCommands=len(scope['omittedCommands']), omittedCases=len(scope['omittedCases']))
    print('M_TEST_START ' + json.dumps(summary, ensure_ascii=False), flush=True)
    print(f'從 {scope["startStage"]} 第 {scope["startStep"]} 步開始；只執行所選位置及後續步驟。', flush=True)
    if scope['releaseStep']:
        print('Release 起始模組：' + scope['releaseStep'], flush=True)
    if scope['fromCase']:
        print('起始案例：' + scope['fromCase'], flush=True)
    if not scope['fullMAcceptance']:
        print('SCOPED CHECK: 略過的步驟不視為已通過，本次結果不認證完整 M 階段。', flush=True)
    if args.dry_run:
        print('M_TEST_PLAN ' + json.dumps(plan, ensure_ascii=False), flush=True)
        return 0
    result = Gates(root).run(plan, {'M_REQUIRE_DOCKER':'1'}, scope=scope)
    return 0 if result['status'] in ('passed','scoped_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
