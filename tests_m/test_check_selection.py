"""Start menus, source-owned tail selection and preserved acceptance boundaries."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
from platform_m.gates import Gates, plans, release_step_count
from scripts.check_m import main
from scripts.check_start_selection import (
    SelectionCancelled, case_ids, choose, release_plan, release_tail, select_start, selected_plan,
)

ROOT = Path(__file__).resolve().parents[1]
PERFECT = 'gepa_test.GepaWorkflowTests.test_perfect_seed_skips_proposals_and_cannot_release_without_improvement'
FINAL = 'gepa_test.GepaWorkflowTests.test_real_optimizer_runner_final_isolation_approval_rollback_and_tamper_gate'


def fixture_plan():
    return [(f'M{i}', [[sys.executable, '-c', f'print("M{i}-1")'],
                       [sys.executable, '-c', f'print("M{i}-2")']]) for i in range(1,8)]


def test_numbered_choices_reject_invalid_input_and_cancel_without_defaulting():
    answers = iter(['', '9', '-1', 'garbage', '2'])
    with redirect_stdout(io.StringIO()):
        assert choose('Start', ['one','two'], lambda _:next(answers)) == 1
    for value in ('0','q'):
        with pytest.raises(SelectionCancelled), redirect_stdout(io.StringIO()):
            choose('Start', ['one'], lambda _:value)
    with pytest.raises(SelectionCancelled), redirect_stdout(io.StringIO()):
        choose('Start', ['one'], lambda _:(_ for _ in ()).throw(EOFError()))


def test_stage_and_step_selection_preserves_original_order_and_does_not_mutate_plan():
    plan = fixture_plan()
    selected, scope = selected_plan(plan, ROOT, 'M4', 2)
    assert selected[0] == ('M4',[plan[3][1][1]])
    assert [name for name,_ in selected] == ['M4','M5','M6','M7']
    assert len(scope['omittedCommands']) == 7
    assert scope['commandOffsets'] == {'M4':1}
    assert scope['fullMAcceptance'] is False
    assert len(plan[3][1]) == 2
    assert selected_plan(plan,ROOT,'M1',1)[1]['fullMAcceptance'] is True


@pytest.mark.parametrize('stage,step', [('M8',1),('M7',0),('M7',3),('M7',True)])
def test_unknown_stage_and_out_of_range_steps_fail(stage,step):
    with pytest.raises(ValueError):
        selected_plan(fixture_plan(),ROOT,stage,step)


def test_menu_drills_into_m7_release_and_skips_ten_passed_gepa_cases():
    plan = plans(ROOT,sys.executable)
    catalog = release_plan(ROOT,'python','node')
    release_index = [name for name,_ in catalog].index('python-gepa_test') + 1
    answers = iter(['7','5',str(release_index),'11'])
    with redirect_stdout(io.StringIO()):
        selected,scope = select_start(plan,ROOT,catalog,interactive=True,read=lambda _:next(answers))
    assert [stage for stage,_ in selected] == ['M7']
    assert len(selected[0][1]) == 3
    command = selected[0][1][0]
    assert command[-4:] == ['--from-step','python-gepa_test','--from-case',PERFECT]
    assert len(scope['omittedCases']) == 10
    assert scope['fromCase'] == PERFECT
    tail,omitted = release_tail(catalog,ROOT,'python-gepa_test',PERFECT)
    from scripts.gepa_validation_budget import expand_plan
    expanded = expand_plan(tail,ROOT)
    assert [cmd[-1] for name,cmd in expanded if name.startswith('python-gepa_test--')] == [PERFECT,FINAL]
    assert expanded[0][0] == 'filesystem-calibration'
    assert 'all-frontend' in omitted and 'filesystem-calibration' not in omitted
    assert release_step_count(ROOT,command) == len(expanded)


def test_release_case_must_belong_to_selected_module_before_dispatch():
    plan = plans(ROOT,sys.executable)
    catalog = release_plan(ROOT,'python','node')
    for module,case in [('not-a-step',None), ('all-frontend',PERFECT), ('python-warmup_test',PERFECT)]:
        with pytest.raises(ValueError):
            selected_plan(plan,ROOT,'M7',5,release=module,case=case,catalog=catalog)
    with pytest.raises(ValueError):
        selected_plan(plan,ROOT,'M7',6,release='python-gepa_test',case=PERFECT,catalog=catalog)
    assert case_ids(ROOT,'gepa_test.py')[-2:] == [PERFECT,FINAL]
    with pytest.raises(ValueError):
        case_ids(ROOT,'../gepa_test.py')


def test_ruff_file_arguments_are_not_mistaken_for_the_release_executable():
    from scripts.check_start_selection import is_release_command
    m7=dict(plans(ROOT,sys.executable))['M7']
    assert is_release_command(m7[4])
    assert not is_release_command(m7[5])
    assert not is_release_command(m7[6])
    assert 'scripts/check_steps.py' in m7[5]


def test_cli_noninteractive_and_dry_run_never_prompt_or_construct_gates():
    with patch('scripts.check_m.sys.stdin.isatty',return_value=False), \
         patch('builtins.input',side_effect=AssertionError('must not prompt')), \
         patch('scripts.check_m.Gates') as runner, redirect_stdout(io.StringIO()) as output:
        assert main(['--from-stage','M7','--from-step','6','--dry-run']) == 0
        runner.assert_not_called()
    assert 'SCOPED CHECK' in output.getvalue()
    preview=json.loads(next(line.removeprefix('M_TEST_PLAN ') for line in output.getvalue().splitlines() if line.startswith('M_TEST_PLAN ')))
    assert len(preview)==1 and len(preview[0][1])==2
    assert preview[0][1][0][1:4]==['-m','ruff','check']


def test_cli_tty_asks_numbered_stage_and_step_and_can_cancel_before_dispatch():
    with patch('scripts.check_m.sys.stdin.isatty',return_value=True), \
         patch('builtins.input',side_effect=['7','6']),patch('scripts.check_m.Gates') as runner, \
         redirect_stdout(io.StringIO()) as output:
        assert main(['--dry-run']) == 0
        runner.assert_not_called()
    assert '選擇起始階段' in output.getvalue() and '選擇 M7 的起始步驟' in output.getvalue()
    with patch('builtins.input',side_effect=EOFError()),patch('scripts.check_m.Gates') as runner,redirect_stdout(io.StringIO()):
        assert main(['--interactive']) == 130
        runner.assert_not_called()


def test_explicit_noninteractive_mode_keeps_full_ci_acceptance_without_input():
    with patch('scripts.check_m.sys.stdin.isatty',return_value=True), \
         patch('builtins.input',side_effect=AssertionError('CI prompt')), \
         patch('scripts.check_m.Gates') as runner,redirect_stdout(io.StringIO()):
        runner.return_value.run.return_value = {'status':'passed'}
        assert main(['--non-interactive']) == 0
        assert runner.return_value.run.call_args.kwargs['scope']['fullMAcceptance'] is True
        assert len(runner.return_value.run.call_args.args[0]) == 7


@pytest.mark.parametrize('arguments', [
    ['--from-step','5','--dry-run'],['--from-stage','M7','--from-step','0','--dry-run'],
    ['--from-stage','M7','--from-step','6','--from-case',PERFECT,'--dry-run'],
    ['--profile','components','--from-stage','M7'],
])
def test_cli_invalid_selection_cannot_start_tests(arguments):
    with patch('scripts.check_m.Gates') as runner,pytest.raises(SystemExit) as exc:
        main(arguments)
    assert exc.value.code == 2
    runner.assert_not_called()


def test_real_selected_children_skip_earlier_commands_keep_indices_and_do_not_certify_acceptance(tmp_path):
    subprocess.run(['git','init',str(tmp_path)],check=True,capture_output=True)
    marker = tmp_path/'visited.txt'
    def cmd(value):
        return [sys.executable,'-c',f'from pathlib import Path;p=Path({str(marker)!r});p.open("a").write({value!r})']
    full = [('M1',[cmd('never-M1')]),('M7',[cmd('never-first'),cmd('second'),cmd('third')])]
    selected,scope = selected_plan(full,tmp_path,'M7',2)
    runner = Gates(tmp_path)
    with redirect_stdout(io.StringIO()) as output:
        result = runner.run(selected,scope=scope)
    assert result['status'] == 'scoped_passed'
    assert marker.read_text() == 'secondthird'
    assert 'command=2/3' in output.getvalue() and 'command=3/3' in output.getvalue()
    bundle = json.loads((runner.directory/'M7.json').read_text())
    assert [row['command_index'] for row in bundle['logs']] == [1,2]
    assert result['scope']['fullMAcceptance'] is False
    with runner.store.db() as db:
        assert db.execute('SELECT count(*) FROM checks').fetchone()[0] == 0


def test_selected_failure_still_blocks_successors_and_exports_exact_scope(tmp_path):
    subprocess.run(['git','init',str(tmp_path)],check=True,capture_output=True)
    plan = [('M1',[[sys.executable,'-c','raise SystemExit(99)']]),
            ('M6',[[sys.executable,'-c','raise SystemExit(3)']]),
            ('M7',[[sys.executable,'-c','raise SystemExit("must not execute")']])]
    selected,scope = selected_plan(plan,tmp_path,'M6',1)
    runner = Gates(tmp_path)
    with redirect_stdout(io.StringIO()):
        result=runner.run(selected,scope=scope)
    assert result['status'] == 'blocked'
    assert [row['status'] for row in result['checks']] == ['failed','blocked']
    import zipfile
    with zipfile.ZipFile(runner.directory/'support.zip') as archive:
        saved=json.loads(archive.read('report.json'))
        assert saved['scope']['startStage'] == 'M6'
        assert 'M1.json' not in archive.namelist()
