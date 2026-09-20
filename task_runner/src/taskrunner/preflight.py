"""Gate qualification on disposable copies of the untouched repository."""
import os
import re
import subprocess
import tempfile
import uuid

from . import checks, gitops, record


def check_gates(wf):
    source = gitops.Git(wf.root)
    if not source.is_clean():
        raise record.RecordError('check-gates requires a clean work tree; commit or remove changes first')
    runs = record.ensure_runs_dir(source.top)
    with record.Lock(runs).acquire('check-gates'):
        directory = os.path.join(runs, 'check-gates', str(uuid.uuid4()))
        os.makedirs(directory)
        planned = []
        for task in wf.tasks:
            if task['kind'] == 'produce':
                for n, gate in enumerate(task['gates'], 1):
                    planned.append((task, f"{task['id']}:gate:{n}", gate))
            elif task['kind'] == 'check':
                for n, command in enumerate(task['run'], 1):
                    planned.append((task, f"{task['id']}:check:{n}", {'run': command, 'new': False}))
        results = []
        for number, (task, name, gate) in enumerate(planned, 1):
            with tempfile.TemporaryDirectory(prefix='task-runner-gates-') as tmp:
                root = os.path.join(tmp, 'repo')
                subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '-q', '--no-hardlinks',
                                '--', source.top, root], check=True, capture_output=True)
                git = gitops.Git(root)
                cwd = os.path.join(root, os.path.relpath(wf.root, source.top))
                log = os.path.join(directory, f'{number}.log')
                ran = checks.run_commands([gate['run']], cwd=cwd, log_path=log,
                                           timeout_s=task['gate_timeout_min'] * 60,
                                           env=checks.command_env(os.environ))[-1]
                status = ran['result']
                if status in ('timeout', 'error'):
                    status = 'error'
                intended = False
                if gate.get('new'):
                    if status == 'fail':
                        intended = bool(re.search(gate.get('fail_pattern', ''), ran['tail']))
                        if not intended:
                            status = 'error'
                    elif status == 'pass':
                        status = 'objection'
                litter = git.dirty_paths()
                embedded = git.embedded_repositories()
                if litter or embedded:
                    status = 'error'
                results.append({'id': name, 'command': gate['run'], 'new': gate.get('new', False),
                                'result': status, 'fails_as_intended': intended, 'exit': ran['exit'],
                                'changed_paths': litter, 'embedded_repositories': embedded, 'log': log})
        report = {'results': results, 'ok': all(r['result'] == 'pass' or
                  (r['result'] == 'fail' and r['fails_as_intended']) for r in results)}
        record.write_durable(os.path.join(directory, 'results.json'), record.dump_json(report))
        report['directory'] = directory
        return report
