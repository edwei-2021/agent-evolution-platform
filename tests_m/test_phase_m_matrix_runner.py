"""The unattended runner must certify repetitions and keep failure evidence."""
import json
from types import SimpleNamespace
import zipfile

from scripts import check_m_matrix as matrix
from scripts import check_m
from platform_m.gates import FIRST_RUN_SECONDS, plans
from matrix_scenarios import ROUND_BATCHES


def fake_checkout(monkeypatch):
    monkeypatch.setattr(matrix, 'source_snapshot', lambda root: ('frozen-source', {}))
    monkeypatch.setattr(matrix.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout='fixed-head\n'))


def test_every_new_stage_command_has_a_first_run_budget():
    for stage, commands in plans(matrix.ROOT, str(matrix.ROOT/'.venv-m/bin/python')):
        assert len(commands) == len(FIRST_RUN_SECONDS[stage]), stage


def test_three_rounds_require_all_configurations_and_all_seven_stages(tmp_path, monkeypatch):
    fake_checkout(monkeypatch)
    monkeypatch.setattr(matrix, 'release_step_names', lambda root: ['python-fixture'])
    monkeypatch.setattr(matrix, 'WORKFLOW_MODULES', {'fixture-workflow': ('python-fixture',)})
    monkeypatch.setattr(matrix, 'VARIANT_MODULES', {})
    monkeypatch.setattr(matrix, 'covered_flow_paths', lambda steps: dict.fromkeys(matrix.FLOW_PATHS, True))
    catalog = matrix.catalog_v3()
    monkeypatch.setattr(matrix, 'read_round_variant', lambda root, child, steps, number: [
        {'batch': batch, 'taskIds': sorted(matrix.catalog_batch(catalog, batch)),
         'round': number, 'taskCallBudget': 5+number, 'maxSeconds': 4450+(number-1)*130}
        for batch in ROUND_BATCHES[number-1]])
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
    assert result['coverage']['workflowPasses'] == {'fixture-workflow': 3}
    assert result['coverage']['ratePercent'] == 100
    assert result['coverage']['minimumRatePercent'] == 60
    assert result['coverage']['modelQuestionRatePercent'] == 100
    assert result['coverage']['distinctV3Batches'] == [0, 1, 2, 3, 4]
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


def test_each_runtime_workflow_and_provider_bank_variant_requires_nonempty_passed_release_evidence():
    from runtime_service import WORKFLOW_TASKS
    assert set(matrix.WORKFLOW_MODULES) == set(WORKFLOW_TASKS)
    prefixes = {prefix for group in (*matrix.WORKFLOW_MODULES.values(),
                                    *matrix.VARIANT_MODULES.values()) for prefix in group}
    available = set(matrix.release_step_names(matrix.ROOT))
    assert all(any(step == prefix or step.startswith(prefix+'--') for step in available)
               for prefix in prefixes)
    rows = [{'step': prefix, 'status': 'completed', 'testCases': [{'status': 'passed'}]}
            for prefix in prefixes]
    assert all(matrix.covered_workflows(rows).values())
    for prefix in prefixes:
        missing = [row for row in rows if row['step'] != prefix]
        assert not all(matrix.covered_workflows(missing).values()), prefix
        empty = [{**row, 'testCases': []} if row['step'] == prefix else row for row in rows]
        assert not all(matrix.covered_workflows(empty).values()), prefix


def test_round_workloads_have_distinct_batches_and_nonrepeated_parameters(tmp_path):
    from matrix_scenarios import round_parameters
    from scripts.check_m_matrix import read_round_variant
    combinations = [round_parameters(n) for n in (1, 2, 3)]
    assert len({row['taskCallBudget'] for row in combinations}) == 3
    assert len({row['maxSeconds'] for row in combinations}) == 3
    assert set.union(*(set(row['batches']) for row in combinations)) == set(range(5))
    catalog = matrix.catalog_v3()
    report = tmp_path/'report.json'
    steps = [{'step': matrix.V3_STEP_PREFIX+name, 'log': matrix.V3_STEP_PREFIX+name+'.log',
              'testCases': [{'test': 'challenge_v3_workflow_test.ChallengeV3WorkflowTests.'+name,
                             'status': 'passed'}]} for name in matrix.V3_METHODS]
    for row in combinations:
        entries = [{'round': row['round'], 'batch': batch, 'taskCallBudget': row['taskCallBudget'],
                    'maxSeconds': row['maxSeconds'], 'taskIds': sorted(matrix.catalog_batch(catalog, batch)),
                    'datasetHash': 'a'*64} for batch in row['batches']]
        for step, entry in zip(steps, entries):
            (tmp_path/step['log']).write_text('M_MATRIX_V3 '+json.dumps(entry)+'\n')
        assert read_round_variant(tmp_path, report, steps, row['round']) == sorted(entries, key=lambda value: value['batch'])
        entries[1]['taskIds'].pop()
        (tmp_path/steps[1]['log']).write_text('M_MATRIX_V3 '+json.dumps(entries[1])+'\n')
        import pytest
        with pytest.raises(ValueError, match='questions'):
            read_round_variant(tmp_path, report, steps, row['round'])


def test_finite_path_coverage_reports_denominator_missing_paths_and_partial_rate():
    catalog = matrix.catalog_v3()
    empty = matrix.coverage_report([], [], catalog)
    assert (empty['coveredPaths'], empty['totalPaths'], empty['ratePercent']) == (0, 103, 0)
    assert empty['minimumRatePercent'] == 60
    partial = matrix.coverage_report([{'status': 'passed', 'configurationsPassed': sorted(matrix.CONFIG_IDS)}], [], catalog)
    assert (partial['coveredPaths'], partial['totalPaths']) == (72, 103)
    assert partial['ratePercent'] > 60
    assert partial['modelQuestionRatePercent'] == 0
    assert len(partial['missingPaths']) == 31


def test_strata_provider_paths_require_three_individual_passed_workflows():
    rows = [{'step': 'python-strata_workflow_test', 'status': 'completed', 'testCases': [
        {'test': 'strata_workflow_test.StrataWorkflows.test_llm_reflection_review_approval_and_rollback',
         'status': 'passed'}]}]
    paths = matrix.covered_flow_paths(rows)
    assert paths['llm-evolution:strata']
    assert not paths['nanobot-repair:strata']
    assert not paths['gepa-evolution:strata']


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
