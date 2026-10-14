"""Source-owned test menus and scoped start plans; no SDK probes or test dispatch."""
import ast
from pathlib import Path

STAGES = {
    'M1': '資料遷移與前端', 'M2': '契約與 nanobot bridge', 'M3': '排程、租約與持續化',
    'M4': 'Docker 環境與隔離', 'M5': '評估與資料隔離', 'M6': '核准、簽章與版本',
    'M7': 'API、整合回歸與靜態檢查',
}
M7_STEPS = ['API 與安全性', '監督器與接續選單', '原始碼掃描', 'SDK 環境檢查',
            'Release 回歸（可再選模組與案例）', 'Ruff 檢查', 'TypeScript 檢查']


class SelectionCancelled(Exception):
    pass


def choose(title, labels, read=None):
    read = read or input
    print('\n' + title, flush=True)
    for index, label in enumerate(labels, 1):
        print(f'  {index}. {label}', flush=True)
    print('  0. 取消，不執行測試', flush=True)
    while True:
        try:
            value = read(f'請選擇 1–{len(labels)}（0 取消）：').strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise SelectionCancelled() from exc
        if value.lower() in {'0', 'q'}:
            raise SelectionCancelled()
        if value.isascii() and value.isdigit() and 1 <= int(value) <= len(labels):
            return int(value) - 1
        print('選項無效，請輸入畫面上的編號。', flush=True)


def release_plan(root, python, node):
    root = Path(root)
    return [('filesystem-calibration', [python, str(root/'scripts/calibrate_release_tests.py')]),
            ('all-frontend', [node, '--test', *map(str, sorted((root/'tests').glob('*.test.js')))])] + [
        ('python-' + path.stem, [python, str(root/'scripts/run_test_module.py'), path.name,
                                 '--tests-dir', str(root/'tests')])
        for path in sorted((root/'tests').glob('*_test.py'))]


def case_ids(root, pattern):
    if Path(pattern).name != pattern or not pattern.endswith('_test.py'):
        raise ValueError('Expected a source-owned *_test.py module')
    tree = ast.parse((Path(root)/'tests'/pattern).read_text())
    return sorted(pattern[:-3] + '.' + cls.name + '.' + fn.name
                  for cls in tree.body if isinstance(cls, ast.ClassDef)
                  for fn in cls.body if isinstance(fn, ast.FunctionDef) and fn.name.startswith('test_'))


def release_tail(plan, root, start, case=None):
    names = [name for name, _ in plan]
    if start not in names:
        raise ValueError('Unknown release step: ' + str(start))
    index = names.index(start)
    selected = [(name, list(command)) for name, command in plan[index:]]
    if case:
        if not start.startswith('python-'):
            raise ValueError('A test case requires a Python release module')
        pattern = start.removeprefix('python-') + '.py'
        if case not in case_ids(root, pattern):
            raise ValueError('Unknown case for selected release module: ' + case)
        selected[0][1].extend(['--from-case', case])
    if index:
        selected.insert(0, (plan[0][0], list(plan[0][1])))  # required budget calibration; no model requests
    return selected, [name for name in names[:index] if name != 'filesystem-calibration']


def is_release_command(command):
    return len(command) > 1 and Path(command[1]).name == 'check_steps.py'


def step_label(stage, index, command):
    if stage == 'M7' and index < len(M7_STEPS):
        return M7_STEPS[index]
    if '--test' in command:
        return '前端測試（Node.js）'
    return ' '.join(str(arg) for arg in command[1:])


def selected_plan(plan, root, stage, step, *, release=None, case=None, catalog=None):
    names = [name for name, _ in plan]
    if stage not in names:
        raise ValueError('Unknown M stage: ' + str(stage))
    first = names.index(stage)
    commands = plan[first][1]
    if type(step) is not int or not 1 <= step <= len(commands):
        raise ValueError(f'{stage} step must be between 1 and {len(commands)}')
    chosen = [(name, [list(command) for command in cmds]) for name, cmds in plan[first:]]
    chosen[0] = (stage, chosen[0][1][step-1:])
    omitted = [{'stage':name, 'step':index+1, 'label':step_label(name,index,command)}
               for stage_index,(name,cmds) in enumerate(plan) for index,command in enumerate(cmds)
               if stage_index < first or (stage_index == first and index < step-1)]
    if release or case:
        command = chosen[0][1][0]
        if stage != 'M7' or step != 5 or not is_release_command(command) or not release:
            raise ValueError('Release module/case selection requires M7 step 5 and --release-step')
        _, skipped = release_tail(catalog or [], root, release, case)
        command.extend(['--from-step', release])
        if case:
            command.extend(['--from-case', case])
    else:
        skipped = []
    omitted_cases = []
    if case:
        ids = case_ids(root, release.removeprefix('python-') + '.py')
        omitted_cases = ids[:ids.index(case)]
    full = first == 0 and step == 1 and not release and not case
    scope = {'kind':'manual-start', 'startStage':stage, 'startStep':step,
             'releaseStep':release, 'fromCase':case, 'fullMAcceptance':full,
             'fullM7Acceptance':full, 'priorEvidence':'omitted steps were not executed or re-certified',
             'omittedCommands':omitted, 'omittedReleaseSteps':skipped, 'omittedCases':omitted_cases,
             'commandOffsets':{stage:step-1}, 'stageCommandCounts':{name:len(cmds) for name,cmds in plan}}
    return chosen, scope


def select_start(plan, root, catalog, *, stage=None, step=None, release=None, case=None,
                 interactive=False, read=None):
    if interactive:
        names = [name for name, _ in plan]
        if stage is None:
            stage = names[choose('選擇起始階段（將執行所選位置及後續步驟）',
                                 [name + ' — ' + STAGES.get(name, name) for name in names], read)]
        if stage not in names:
            raise ValueError('Unknown M stage: ' + str(stage))
        commands = plan[names.index(stage)][1]
        if step is None:
            step = choose(f'選擇 {stage} 的起始步驟',
                          [step_label(stage,index,command) for index,command in enumerate(commands)], read) + 1
        if stage == 'M7' and step == 5:
            if release is None:
                release = catalog[choose('選擇 Release 起始步驟（必要的校準會自動執行）',
                                          [name for name, _ in catalog], read)][0]
            if case is None and release.startswith('python-'):
                ids = case_ids(root, release.removeprefix('python-') + '.py')
                if not ids:
                    raise ValueError('Selected module has no known test cases')
                case = ids[choose('選擇起始測試案例（前面的案例將略過）', ids, read)]
    return selected_plan(plan, root, stage or 'M1', step if step is not None else 1,
                         release=release, case=case, catalog=catalog)
