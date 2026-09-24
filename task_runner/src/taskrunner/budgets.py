"""Budget reservations live in agent intents; settlement is one durable state transition."""


class Paused(Exception):
    """The owner asked for a pause (`runner pause`); raised only where a call is about to start,
    so the run stops with the same bookkeeping as a budget stop and nothing in flight is lost."""


class Exhausted(Exception):
    """No call may start: the dollar budget (`hint` --add-budget) or, for agents that report no
    cost, the token cap (`hint` --add-tokens) is used up."""

    def __init__(self, message, hint="--add-budget USD"):
        super().__init__(message)
        self.hint = hint


def cap_for(agent, task):
    return float(task['budget_usd']) if agent.reports_cost else 0.0


def tokens_used(state):
    unpriced = state['spend']['unpriced']
    return unpriced['tokens_in'] + unpriced['tokens_out']


def token_cap(state):
    """0 means no cap: runs recorded before the cap existed have none."""
    return int(state.get('run_budget_tokens', 0) or 0)


def fits_tokens(state, agent):
    """An agent that reports no dollar cost may start a call only while the run's unpriced usage
    is under `run_budget_tokens`. Usage arrives when a call ends, so the cap is a stop line, not a
    ceiling: the call that crosses it completes. Interrupted calls have unknown usage and are not
    counted."""
    if agent.reports_cost or not token_cap(state):
        return True
    return tokens_used(state) < token_cap(state)


def token_stop(state, what):
    return Exhausted(f"the token cap for agents that report no cost is used up "
                     f"({tokens_used(state)} of {token_cap(state)} tokens) before {what}",
                     hint="--add-tokens N")


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
