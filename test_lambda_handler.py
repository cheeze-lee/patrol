"""Unit tests for lambda_handler parsing/routing"""

import os
import unittest

import lambda_handler


class TestLambdaHandlerRepoRouting(unittest.TestCase):
    def setUp(self):
        self._old_map = os.environ.get('REPOSITORY_URL_MAP')
        self._old_default = os.environ.get('DEFAULT_REPOSITORY_URL')

    def tearDown(self):
        if self._old_map is None:
            os.environ.pop('REPOSITORY_URL_MAP', None)
        else:
            os.environ['REPOSITORY_URL_MAP'] = self._old_map

        if self._old_default is None:
            os.environ.pop('DEFAULT_REPOSITORY_URL', None)
        else:
            os.environ['DEFAULT_REPOSITORY_URL'] = self._old_default

    def test_routes_repo_by_service_name_when_missing_repo_url(self):
        os.environ['REPOSITORY_URL_MAP'] = '{"svc-a":"https://github.com/org/repo-a","svc-b":"https://github.com/org/repo-b"}'
        os.environ.pop('DEFAULT_REPOSITORY_URL', None)

        otel = {
            'resourceLogs': [
                {
                    'resource': {
                        'attributes': {
                            'service.name': 'svc-b',
                        }
                    },
                    'scopeLogs': [
                        {
                            'logRecords': [
                                {
                                    'timeUnixNano': '1707817200000000000',
                                    'severityNumber': 17,
                                    'severityText': 'ERROR',
                                    'body': {'stringValue': 'boom'},
                                    'attributes': {
                                        'exception.type': 'TypeError',
                                        'exception.message': 'boom',
                                        'exception.stacktrace': 'at fn (src/a.ts:10:2)',
                                        'code.filepath': 'src/a.ts',
                                        'code.lineno': 10,
                                    },
                                    'traceId': 'abc',
                                    'spanId': 'def',
                                }
                            ]
                        }
                    ],
                }
            ]
        }

        events = lambda_handler._parse_event(otel)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].repository_url, 'https://github.com/org/repo-b')

    def test_default_repo_url_is_used_when_no_mapping_match(self):
        os.environ['REPOSITORY_URL_MAP'] = '{"svc-a":"https://github.com/org/repo-a"}'
        os.environ['DEFAULT_REPOSITORY_URL'] = 'https://github.com/org/default-repo'

        otel = {
            'resourceLogs': [
                {
                    'resource': {
                        'attributes': {
                            'service.name': 'unknown-svc',
                        }
                    },
                    'scopeLogs': [
                        {
                            'logRecords': [
                                {
                                    'timeUnixNano': '1707817200000000000',
                                    'severityNumber': 17,
                                    'severityText': 'ERROR',
                                    'body': {'stringValue': 'boom'},
                                    'attributes': {
                                        'exception.type': 'TypeError',
                                        'exception.message': 'boom',
                                    },
                                    'traceId': 'abc',
                                    'spanId': 'def',
                                }
                            ]
                        }
                    ],
                }
            ]
        }

        events = lambda_handler._parse_event(otel)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].repository_url, 'https://github.com/org/default-repo')

    def test_existing_repo_url_is_not_overridden(self):
        os.environ['REPOSITORY_URL_MAP'] = '{"svc-a":"https://github.com/org/repo-a"}'
        os.environ['DEFAULT_REPOSITORY_URL'] = 'https://github.com/org/default-repo'

        otel = {
            'resourceLogs': [
                {
                    'resource': {
                        'attributes': {
                            'service.name': 'svc-a',
                            'git.repository.url': 'https://github.com/org/real-repo',
                        }
                    },
                    'scopeLogs': [
                        {
                            'logRecords': [
                                {
                                    'timeUnixNano': '1707817200000000000',
                                    'severityNumber': 17,
                                    'severityText': 'ERROR',
                                    'body': {'stringValue': 'boom'},
                                    'attributes': {
                                        'exception.type': 'TypeError',
                                        'exception.message': 'boom',
                                    },
                                    'traceId': 'abc',
                                    'spanId': 'def',
                                }
                            ]
                        }
                    ],
                }
            ]
        }

        events = lambda_handler._parse_event(otel)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].repository_url, 'https://github.com/org/real-repo')


if __name__ == '__main__':
    unittest.main()
