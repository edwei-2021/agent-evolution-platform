"""Frozen, bounded exploration policy (多候選探索); release gates stay separate."""
import random

POLICY = 'failure-diversity-v2'
OPERATIONS = ('rewrite', 'replace', 'reorder', 'compress')
OPERATION_GUIDANCE = {
    'rewrite': 'Start from a blank outline and write 3-6 actionable steps. Do not preserve the parent sentence structure.',
    'replace': 'Replace an unhelpful assumption or step with a concrete action grounded in the observed training failures.',
    'reorder': 'Change the order of diagnosis, policy checking, editing and testing so the observed failure is caught earlier.',
    'compress': 'Remove generic reminders. Keep only decision rules that connect an observed failure to a permitted corrective action.',
}


def adaptive(config):
    return exploring(config) and config.get('explorationPolicy') == POLICY


def instruction_key(body):
    # Formatting alone is not a new repair strategy. Keep original text intact.
    return ' '.join(body.split())


def duplicate_of(body, proposals, baseline):
    key = instruction_key(body)
    if key == instruction_key(baseline):
        return 'baseline'
    return next((p['id'] for p in proposals if instruction_key(p['body']) == key), None)


def duplicate_streak(proposals, baseline):
    streak = 0
    for i in range(len(proposals)-1, -1, -1):
        if duplicate_of(proposals[i]['body'], proposals[:i], baseline) is None:
            break
        streak += 1
    return streak


def reflection_temperature(config, proposals):
    if not adaptive(config):
        return 0
    streak = duplicate_streak(proposals, config['baseline']['skill']['body'])
    return 1.0 if streak >= 2 else 0.7


def failure_lessons(training, proposals):
    """Retain failed tasks and recovered write rejections from training only."""
    failures = {}
    for trace in [t for p in proposals for t in p.get('training', [])] + training:
        errors = list(dict.fromkeys(t['error'][:1600] for t in trace.get('tools', []) if t.get('error')))
        if trace.get('score', 1) >= 1 and not errors:
            continue
        feedback = trace.get('feedback', {})
        previous = failures.get(trace['taskId'], {})
        failures[trace['taskId']] = {'taskId': trace['taskId'], 'rolloutId': trace['rolloutId'],
            'score': trace['score'], 'taskOutcome': trace.get('taskOutcome'),
            'toolRejections': list(dict.fromkeys(previous.get('toolRejections', []) + errors))[-3:],
            'tests': {s: {k: feedback[s].get(k) for k in ('passed', 'total')}
                      for s in ('visible', 'hidden') if isinstance(feedback.get(s), dict)}}
    return list(failures.values())[-4:]

STRATEGIES = (
    ('contract', 'Derive a compact checklist from the task contract. Preserve its actual function signature; remove unrelated legacy examples.'),
    ('boundaries', 'Use boundary partitions and counterexamples to guide repairs, including empty, equal, negative and invalid inputs where applicable.'),
    ('tool-policy', 'Check the allowed Python grammar before writing. Translate unsupported constructs into permitted equivalents and learn from rejection feedback.'),
    ('invariants', 'Track algorithm invariants and state transitions; check ordering, duplicates and loop termination against the contract.'),
    ('minimal-repair', 'Locate the earliest incorrect behavior, make a justified minimal repair, then inspect whether interacting defects remain.'),
    ('budget', 'Plan bounded tool use, leave room for testing and the final summary, and avoid repeating unchanged rejected writes.'),
    ('input-preservation', 'Check input preservation, aliasing and output types; choose nonmutating operations when required.'),
    ('failure-recovery', 'Classify test failures and tool rejections separately, change the underlying approach after repeated rejection, and retest.'),
    ('generalization', 'Derive behavior from requirements and failure categories; avoid hardcoding examples or assuming visible tests cover the contract.'),
    ('control-flow', 'Inspect preconditions, early returns and exception paths before changing the main algorithm.'),
    ('test-interpretation', 'Compare observed test evidence with the proposed invariant and use it to decide the next edit or completion step.'),
    ('concise-workflow', 'Synthesize a short actionable repair workflow from training evidence, eliminating redundant or contradictory instructions.'),
    ('representation', 'Inspect data representation and numeric or textual conversion assumptions before implementing a repair.'),
    ('stable-order', 'Use requirements to distinguish membership, ordering and stability; check ties and repeated values where relevant.'),
    ('multi-step', 'Plan a small sequence of evidence-driven edits with explicit stopping criteria rather than one speculative rewrite.'),
    ('synthesis', 'Combine complementary lessons from previous candidate instructions into a distinct general repair strategy.'),
)


def exploring(config):
    return config.get('searchMode', 'standard') == 'explore'


def proposal_context(candidate, training, proposals, config):
    value = {'candidate': candidate, 'training': training}
    if exploring(config):
        name, instruction = STRATEGIES[len(proposals) % len(STRATEGIES)]
        value['exploration'] = {'attempt': len(proposals)+1, 'strategy': name,
            'instruction': instruction,
            'diversity': 'Produce a materially different general Skill, even when these training tasks passed. Do not claim improvement without evaluation.',
            'recentInstructions': [p['body'] for p in proposals[-3:]]}
        if adaptive(config):
            prior = list(dict.fromkeys(p['body'] for p in proposals))
            value['exploration'].update(policy=POLICY,
                operation=OPERATIONS[len(proposals) % len(OPERATIONS)],
                operationGuidance=OPERATION_GUIDANCE[OPERATIONS[len(proposals) % len(OPERATIONS)]],
                consecutiveDuplicates=duplicate_streak(proposals, config['baseline']['skill']['body']),
                temperature=reflection_temperature(config, proposals),
                recentInstructions=prior[-3:], failureLessons=failure_lessons(training, proposals),
                diversity='Write a different operational workflow, not a paraphrase, extra reminders, or a copy of prior instructions. '
                          'Use the requested mutation operation. Remove irrelevant legacy examples. '
                          'Use the fixed tool rejection categories even when a task recovered and passed. '
                          'State what observation triggers an action, what to change after rejection, and when to stop. '
                          'Use only training evidence; do not include solution code, task IDs, test answers or claims of improvement.')
    return value


class CoverageSampler:
    """Visit every training ID before repeating, including a short final batch."""
    def __init__(self, size, seed):
        self.size = size
        self.rng = random.Random(seed)
        self.pending = []

    def next_minibatch_ids(self, loader, state):
        if not self.pending:
            self.pending = list(loader.all_ids())
            self.rng.shuffle(self.pending)
        batch, self.pending = self.pending[:self.size], self.pending[self.size:]
        if not batch:
            raise ValueError('Exploration requires nonempty training data')
        return batch


class NovelNonRegression:
    """Equal training scores may reach validation; identical bodies do not."""
    def should_accept(self, proposal, state):
        return (proposal.candidate not in state.program_candidates and
                sum(proposal.subsample_scores_after or []) >= sum(proposal.subsample_scores_before or []))

    def reject_reason(self, proposal, state):
        return 'duplicate-instructions' if proposal.candidate in state.program_candidates else 'training-regression'


def summary(config, ledger, proposals, candidates):
    from gepa_dataset import data_for
    train = {t['id'] for t in data_for(config)['train']}
    tested = {r['taskId'] for r in ledger if r['stage']=='search' and r['taskId'] in train}
    bodies = {p['body'] for p in proposals}
    base = config['baseline']['skill']['body']
    result = {'mode': 'explore', 'seed': config['searchSeed'],
            'trainingTested': len(tested), 'trainingTotal': len(train),
            'generated': len(proposals), 'uniqueNew': len(bodies-{base}),
            'duplicates': len(proposals)-len(bodies-{base}),
            'validatedNew': len(candidates)-1}
    if adaptive(config):
        result.update(policy=POLICY,
            uniqueNew=len({instruction_key(b) for b in bodies}-{instruction_key(base)}),
            duplicates=sum(duplicate_of(p['body'], proposals[:i], base) is not None for i, p in enumerate(proposals)),
            skippedDuplicates=sum(p.get('duplicateOf') is not None for p in proposals),
            savedCandidateEvaluations=sum(p.get('skippedEvaluations', 0) for p in proposals))
    return result
