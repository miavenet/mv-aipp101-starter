"""Budget reservations live in agent intents; settlement is one durable state transition."""


class Exhausted(Exception):
    pass


def cap_for(agent, task):
    return float(task['budget_usd']) if agent.reports_cost else 0.0


def fits(state, amount):
    spend = state['spend']
    return (spend['known_usd'] < state['run_budget_usd']
            and round(spend['known_usd'] + spend['reserved_usd'] + amount, 6)
            <= state['run_budget_usd'])


def settle(state, task_id, reservation, result):
    spend, task = state['spend'], state['tasks'][task_id]
    spend['reserved_usd'] = round(max(0, spend['reserved_usd'] - reservation), 6)
    state['seconds'] += int(result.seconds)
    if result.cost_usd is not None:
        spend['known_usd'] = round(spend['known_usd'] + result.cost_usd, 6)
        task['cost_usd'] = round(task['cost_usd'] + result.cost_usd, 6)
    elif result.status != 'environment':
        unpriced = spend['unpriced']
        unpriced['calls'] += 1
        unpriced['unknown_calls'] += int(not result.usage)
        unpriced['tokens_in'] += int(result.usage.get('tokens_in', 0))
        unpriced['tokens_out'] += int(result.usage.get('tokens_out', 0))
