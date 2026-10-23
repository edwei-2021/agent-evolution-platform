"""The unattended runner must certify repetitions and keep failure evidence."""
import json
from types import SimpleNamespace
import zipfile

from scripts import check_m_matrix as matrix
from scripts import check_m
from platform_m.gates import FIRST_RUN_SECONDS, plans


def fake_checkout(monkeypatch):
    monkeypatch.setattr(matrix, 'source_snapshot', lambda root: ('frozen-source', {}))
    monkeypatch.setattr(matrix.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout='fixed-head\n'))


def test_every_new_stage_command_has_a_first_run_budget():
    for stage, commands in plans(matrix.ROOT, str(matrix.ROOT/'.venv-m/bin/python')):
        assert len(commands) == len(FIRST_RUN_SECONDS[stage]), stage


def test_three_rounds_require_all_configurations_and_all_seven_stages(tmp_path, monkeypatch):
    fake_checkout(monkeypatch)
    monkeypatch.setattr(matrix, 'release_step_names', lambda root: ['python-fixture'])
    calls = []
    config_log = ''.join(f'test_gepa_configuration_freezes_complete_major_option_matrix[{name}] PASSED\n'
                         for name in sorted(matrix.CONFIG_IDS)) + '73 passed in 1.0s\n'
    other_log = ''.join(f'test_other_workflow_option_matrix_{name.split("-", 1)[0]}[{name}] PASSED\n'
                        for name in sorted(matrix.OTHER_IDS)) + '18 passed in 1.0s\n'

    def completed(root, command, log, events, flow, round_number):
        calls.append((flow, round_number))
        if flow == 'configurations':
            output = config_log
        elif flow == 'other-options':
            output = other_log
        elif flow == 'components':
            output = ('Expected fixture: 1 failed before recovery\n'
                      '123 passed, 1 skipped in 10.0s\n123 passed, 1 skipped in 10.0s\n')
        else:
            report = root/'.local/m/support'/f'MCHECK-{round_number}'/'report.json'
            report.parent.mkdir(parents=True, exist_ok=True)
            child = root/'.local/test-reports'/f'CHECK-{round_number}'/'report.json'
            child.parent.mkdir(parents=True, exist_ok=True)
            child.write_text(json.dumps({'profile': 'release', 'status': 'completed',
                                         'steps': [{'step': 'python-fixture', 'status': 'completed',
                                                    'testCases': [{'status': 'passed'}]}]}))
            (report.parent/'M7.json').write_text(json.dumps({'logs': [{'child_report': str(child)}]}))
            report.write_text(json.dumps({'source_hash': 'frozen-source', 'status': 'passed',
                                           'scope': {'fullMAcceptance': True},
                                           'checks': [{'step': f'M{i}', 'status': 'passed'} for i in range(1, 8)]}))
            output = f'Support report: {root}/pytest-of-root/fixture/.local/m/support/MCHECK-x/report.json\nSupport report: {report}\n'
        log.write_text(output)
        return 0, output

    monkeypatch.setattr(matrix, 'run_command', completed)
    output = tmp_path/'matrix'
    assert matrix.run_matrix(tmp_path, plan=[(name, ['fixture']) for name in
                                     ('configurations', 'other-options', 'components', 'acceptance')],
                             output=output) == 0
    result = json.loads((output/'summary.json').read_text())
    assert result['status'] == 'passed'
    assert result['coverage']['flowPasses'] == {'configurations': 3, 'other-options': 3, 'components': 3, 'acceptance': 3}
    assert calls == [(name, number) for name in ('configurations', 'other-options', 'components', 'acceptance')
                     for number in (1, 2, 3)]
    assert all(len(a['configurationsPassed']) == 72 for a in result['attempts'] if a['flow']=='configurations')
    assert all(len(a['otherOptionsPassed']) == 18 for a in result['attempts'] if a['flow']=='other-options')
    with zipfile.ZipFile(output/'support.zip') as archive:
        assert 'summary.json' in archive.namelist()
        assert len([name for name in archive.namelist() if name.endswith('/report.json')]) == 3
        assert len([name for name in archive.namelist() if name.endswith('/release-report.json')]) == 3


def test_missing_configuration_blocks_certification_and_retains_unexecuted_plan(tmp_path, monkeypatch):
    fake_checkout(monkeypatch)
    calls = []
    def incomplete(root, command, log, events, flow, round_number):
        calls.append((flow, round_number))
        output = '1 passed in 0.1s\n'
        log.write_text(output)
        return 0, output
    monkeypatch.setattr(matrix, 'run_command', incomplete)
    output = tmp_path/'matrix'
    assert matrix.run_matrix(tmp_path, plan=[(name, ['fixture']) for name in
                                     ('configurations', 'acceptance')], output=output) == 1
    result = json.loads((output/'summary.json').read_text())
    assert calls == [('configurations', 1)]
    assert result['status'] == 'incomplete'
    assert len(result['coverage']['unexecuted']) == 5
    assert result['attempts'][0]['status'] == 'failed'
    assert (output/'support.zip').is_file()


def test_docker_preparation_failure_is_archived_without_dispatching_matrix(tmp_path, monkeypatch):
    fake_checkout(monkeypatch)
    calls = []
    def fail_build(root, command, log, events, flow, round_number):
        calls.append((flow, round_number))
        log.write_text('Docker image build failed\n')
        return 1, 'Docker image build failed\n'
    monkeypatch.setattr(matrix, 'run_command', fail_build)
    output = tmp_path/'matrix'
    assert matrix.run_matrix(tmp_path, plan=[('configurations', ['fixture'])], output=output,
                             prepare_docker=True) == 1
    summary = json.loads((output/'summary.json').read_text())
    assert calls == [('prepare-docker', 0)]
    assert summary['status'] == 'incomplete'
    assert summary['dockerPreparation']['status'] == 'failed'
    assert len(summary['coverage']['unexecuted']) == 3
    with zipfile.ZipFile(output/'support.zip') as archive:
        assert 'prepare-docker.log' in archive.namelist()


def test_release_omission_is_not_certified(tmp_path, monkeypatch):
    fake_checkout(monkeypatch)
    monkeypatch.setattr(matrix, 'release_step_names', lambda root: ['first', 'missing'])
    def incomplete(root, command, log, events, flow, round_number):
        report = root/'.local/m/support'/'MCHECK-fixture'/'report.json'
        report.parent.mkdir(parents=True, exist_ok=True)
        child = root/'.local/test-reports'/'CHECK-fixture'/'report.json'
        child.parent.mkdir(parents=True, exist_ok=True)
        child.write_text(json.dumps({'profile': 'release', 'status': 'completed',
                                     'steps': [{'step': 'first', 'status': 'completed', 'testCases': []}]}))
        (report.parent/'M7.json').write_text(json.dumps({'logs': [{'child_report': str(child)}]}))
        report.write_text(json.dumps({'source_hash': 'frozen-source', 'status': 'passed',
                                      'scope': {'fullMAcceptance': True},
                                      'checks': [{'step': f'M{i}', 'status': 'passed'} for i in range(1, 8)]}))
        value = f'Support report: {report}\n'
        log.write_text(value)
        return 0, value
    monkeypatch.setattr(matrix, 'run_command', incomplete)
    output = tmp_path/'matrix'
    assert matrix.run_matrix(tmp_path, plan=[('acceptance', ['fixture'])], output=output) == 1
    summary = json.loads((output/'summary.json').read_text())
    assert summary['attempts'][0]['status'] == 'failed'
    assert summary['coverage']['unexecuted'] == [{'flow': 'acceptance', 'round': 2},
                                                  {'flow': 'acceptance', 'round': 3}]


def test_components_entry_consumes_timing_and_reports_real_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_m, 'execute', lambda *args, **kwargs:
                        (0, '125 passed, 1 skipped in 32s', {'elapsed_seconds': 32}))
    assert check_m.main(['--profile', 'components', '--non-interactive'], root=tmp_path) == 0
    output = capsys.readouterr().out
    assert 'M_COMPONENT_TIMING {"elapsed_seconds": 32}' in output
    assert 'COMPONENT CHECK ONLY' in output
    monkeypatch.setattr(check_m, 'execute', lambda *args, **kwargs:
                        (1, '1 failed', {'elapsed_seconds': 1}))
    assert check_m.main(['--profile', 'components', '--non-interactive'], root=tmp_path) == 1
