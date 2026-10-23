"""Declared, distinct V3 workloads for the three unattended matrix rounds."""
import os

ROUND_BATCHES = ((0, 3), (1, 4), (2, 0))


def matrix_round():
    value = os.environ.get('M_MATRIX_ROUND', '1')
    if value not in ('1', '2', '3'):
        raise ValueError('M_MATRIX_ROUND must be 1, 2 or 3')
    return int(value)


def round_parameters(number):
    if type(number) is not int or not 1 <= number <= len(ROUND_BATCHES):
        raise ValueError('Unknown matrix round')
    return {'round': number, 'batches': ROUND_BATCHES[number-1],
            'taskCallBudget': 5 + number, 'maxSeconds': 4450 + (number-1)*130}
