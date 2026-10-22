import copy
import unittest
from scripts.opz_deploy_snapshot import snapshot, literal, verify_runtime


class TestDeploySnapshot(unittest.TestCase):
    def containers(self):
        return [{'Image': 'sha256:' + service, 'Name': '/qopz-' + service + '-1',
                 'Config': {'Labels': {'com.docker.compose.project': 'qopz', 'com.docker.compose.service': service}},
                 'HostConfig': {}, 'Mounts': [], 'NetworkSettings': {'Networks': {}},
                 'State': {'Running': True, 'Health': {'Status': 'healthy'}}}
                for service in ['api', 'control-plane', 'nginx']]

    def test_resource_limits_and_groups_survive(self):
        containers = self.containers()
        containers[0]['HostConfig'] = {'GroupAdd': ['998'], 'Memory': 268435456, 'NanoCpus': 500000000,
            'PidsLimit': 64, 'RestartPolicy': {'Name': 'on-failure', 'MaximumRetryCount': 3}}
        api = snapshot(containers)['services']['api']
        self.assertEqual(api['group_add'], ['998'])
        self.assertEqual(api['mem_limit'], 268435456)
        self.assertEqual(api['cpus'], 0.5)
        self.assertEqual(api['pids_limit'], 64)
        self.assertEqual(api['restart'], 'on-failure:3')

    def test_verifier_refuses_partial_or_unhealthy_recovery(self):
        previous = self.containers()
        verify_runtime(previous, previous)
        current = copy.deepcopy(previous)
        current[0]['Image'] = 'sha256:wrong-release'
        with self.assertRaisesRegex(ValueError, 'configuration differs'):
            verify_runtime(previous, current)
        current = copy.deepcopy(previous)
        current[0]['State']['Health']['Status'] = 'unhealthy'
        with self.assertRaisesRegex(ValueError, 'not healthy'):
            verify_runtime(previous, current)

    def test_existing_proxy_is_included_without_foreign_service(self):
        containers = self.containers()
        proxy = copy.deepcopy(containers[0])
        proxy['Name'] = '/qopz-broker-proxy-1'
        proxy['Config']['Labels']['com.docker.compose.service'] = 'broker-proxy'
        containers.append(proxy)
        self.assertIn('broker-proxy', snapshot(containers)['services'])

    def test_exact_previous_runtime_not_historical_compose(self):
        containers = []
        for service in ['api', 'control-plane', 'nginx']:
            containers.append({'Image': f'sha256:{service}', 'Name': f'/qopz-{service}-1',
                'Config': {'Labels': {'com.docker.compose.project': 'qopz', 'com.docker.compose.service': service},
                           'Env': ['TOKEN=release-A-$secret', 'CUSTOM=preserved'], 'Cmd': ['run-A'], 'Entrypoint': ['entry-A']},
                'HostConfig': {'NetworkMode': 'qopz-net', 'PortBindings': {'80/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8080'}]}},
                'Mounts': [{'Type': 'bind', 'Source': '/opt/qopz/data', 'Destination': '/app/data', 'RW': True}],
                'NetworkSettings': {'Networks': {'qopz-net': {'Aliases': [service]}}}})
        result = snapshot(containers)
        api = result['services']['api']
        self.assertEqual(api['image'], 'sha256:api')
        self.assertEqual(api['environment']['TOKEN'], 'release-A-$secret')
        self.assertEqual(api['command'], ['run-A'])
        self.assertEqual(api['volumes'][0]['source'], '/opt/qopz/data')
        self.assertEqual(api['ports'][0]['host_ip'], '127.0.0.1')
        self.assertEqual(literal(result)['services']['api']['environment']['TOKEN'], 'release-A-$$secret')

    def test_incomplete_snapshot_refused(self):
        with self.assertRaises(ValueError):
            snapshot([])
