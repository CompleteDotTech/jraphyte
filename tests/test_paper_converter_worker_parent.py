import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import venv

from src import paper_converter_worker as worker


class WorkerParentTests(unittest.TestCase):
    def test_direct_parent_and_invalid_pid(self):
        self.assertTrue(worker.controller_parent_matches(os.getppid(), sys.executable, '0' * 64))
        for value in (0, -1, True, None, '123'):
            self.assertFalse(worker.controller_parent_matches(value, sys.executable, '0' * 64))

    def test_only_one_pinned_live_redirector_hop(self):
        executable = str(Path(sys.executable).resolve())
        info = dict(parent_parent_pid=123, parent_executable=executable,
                    parent_executable_sha256='a' * 64, controller_created=1,
                    parent_created=2, worker_created=3, controller_alive=True, parent_alive=True)
        self.assertTrue(worker._redirector_chain_matches(info, 123, executable, 'a' * 64))
        for field, value in (('parent_parent_pid', 456), ('parent_executable', executable + '.other'),
                             ('parent_executable_sha256', 'b' * 64), ('controller_created', 4),
                             ('parent_created', 4), ('worker_created', 1),
                             ('controller_alive', False), ('parent_alive', False)):
            with self.subTest(field=field):
                changed = {**info, field: value}
                self.assertFalse(worker._redirector_chain_matches(changed, 123, executable, 'a' * 64))

    def test_unobservable_windows_parent_fails_closed(self):
        with patch.object(worker.os, 'name', 'nt'), patch.object(worker.os, 'getppid', return_value=456), \
                patch.object(worker, '_windows_parent_info', side_effect=OSError('denied')):
            self.assertFalse(worker.controller_parent_matches(123, sys.executable, 'a' * 64))

    @unittest.skipUnless(os.name == 'nt', 'Windows venv redirector regression')
    def test_genuine_windows_venv_subprocess(self):
        repo = str(Path(worker.__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory() as temporary:
            venv.EnvBuilder(with_pip=False).create(temporary)
            executable = Path(temporary) / 'Scripts' / 'python.exe'
            sha = hashlib.sha256(executable.read_bytes()).hexdigest()
            script = ('import json,os,sys;sys.path.insert(0,' + repr(repo) + ');'
                      'from src.paper_converter_worker import controller_parent_matches;'
                      'print(json.dumps(dict(pid=os.getpid(),ppid=os.getppid(),'
                      'matches=controller_parent_matches(' + str(os.getpid()) + ',' + repr(str(executable)) + ',' + repr(sha) + '),'
                      'wrong_hash=controller_parent_matches(' + str(os.getpid()) + ',' + repr(str(executable)) + ',' + repr('0' * 64) + '))))')
            row = json.loads(subprocess.check_output([str(executable), '-I', '-B', '-c', script], timeout=30))
            self.assertNotEqual(row['ppid'], os.getpid())
            self.assertTrue(row['matches'])
            self.assertFalse(row['wrong_hash'])

    def test_failure_reports_bounded_contract_code(self):
        args = ['worker', '--data-root', 'unused', '--plan', 'unused',
                '--expected-plan-sha256', 'unused', '--output', 'unused']
        for message, expected in (('worker_controller_intent_required', 'worker_controller_intent_required'),
                                  ('private path C:/papers/secret.pdf', None)):
            stderr = io.StringIO()
            with patch.object(sys, 'argv', args), patch.object(worker, 'run', side_effect=ValueError(message)), \
                    contextlib.redirect_stderr(stderr):
                self.assertEqual(worker.main(), 2)
            self.assertEqual(json.loads(stderr.getvalue())['error_code'], expected)

    @unittest.skipUnless(os.name == 'nt', 'Windows process liveness regression')
    def test_terminated_process_exit_259_is_not_alive(self):
        import ctypes
        from ctypes import wintypes as w
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        kernel.WaitForSingleObject.restype = w.DWORD
        kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        kernel.GetExitCodeProcess.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        with subprocess.Popen([sys.executable, '-I', '-B', '-c',
                               'import sys,time;time.sleep(0.3);sys.exit(259)']) as process:
            handle = kernel.OpenProcess(0x101000, False, process.pid)
            self.assertTrue(handle)
            try:
                self.assertTrue(worker._process_handle_alive(kernel, handle))
                self.assertEqual(process.wait(timeout=10), 259)
                exit_code = w.DWORD()
                self.assertTrue(kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)))
                self.assertEqual(exit_code.value, 259)
                self.assertFalse(worker._process_handle_alive(kernel, handle))
            finally:
                kernel.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
