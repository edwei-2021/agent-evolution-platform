"""Frozen, bounded exploration policy (多候選探索); release gates stay separate."""
import random

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
    train = {t['id'] for t in config['datasetSnapshot']['data']['train']}
    tested = {r['taskId'] for r in ledger if r['stage']=='search' and r['taskId'] in train}
    bodies = {p['body'] for p in proposals}
    base = config['baseline']['skill']['body']
    return {'mode': 'explore', 'seed': config['searchSeed'],
            'trainingTested': len(tested), 'trainingTotal': len(train),
            'generated': len(proposals), 'uniqueNew': len(bodies-{base}),
            'duplicates': len(proposals)-len(bodies-{base}),
            'validatedNew': len(candidates)-1}
