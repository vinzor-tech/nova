# Copyright (c) 2012 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests for resource tracker claims."""

import uuid

import mock
from oslo_serialization import jsonutils

from nova.compute import claims
from nova import context
from nova import db
from nova import exception
from nova import objects
from nova.pci import manager as pci_manager
from nova import test
from nova.tests.unit import fake_instance
from nova.tests.unit.pci import fakes as pci_fakes


class FakeResourceHandler(object):
    test_called = False
    usage_is_instance = False

    def test_resources(self, usage, limits):
        self.test_called = True
        self.usage_is_itype = usage.get('name') == 'fakeitype'
        return []


class DummyTracker(object):
    icalled = False
    rcalled = False
    ext_resources_handler = FakeResourceHandler()

    def __init__(self):
        self.new_pci_tracker()

    def abort_instance_claim(self, *args, **kwargs):
        self.icalled = True

    def drop_move_claim(self, *args, **kwargs):
        self.rcalled = True

    def new_pci_tracker(self):
        ctxt = context.RequestContext('testuser', 'testproject')
        self.pci_tracker = pci_manager.PciDevTracker(ctxt)


@mock.patch('nova.objects.InstancePCIRequests.get_by_instance_uuid',
            return_value=objects.InstancePCIRequests(requests=[]))
class ClaimTestCase(test.NoDBTestCase):

    def setUp(self):
        super(ClaimTestCase, self).setUp()
        self.context = context.RequestContext('fake-user', 'fake-project')
        self.resources = self._fake_resources()
        self.tracker = DummyTracker()

    def _claim(self, limits=None, overhead=None, **kwargs):
        numa_topology = kwargs.pop('numa_topology', None)
        instance = self._fake_instance(**kwargs)
        if numa_topology:
            db_numa_topology = {
                    'id': 1, 'created_at': None, 'updated_at': None,
                    'deleted_at': None, 'deleted': None,
                    'instance_uuid': instance.uuid,
                    'numa_topology': numa_topology._to_json()
                }
        else:
            db_numa_topology = None
        if overhead is None:
            overhead = {'memory_mb': 0}
        with mock.patch.object(
                db, 'instance_extra_get_by_instance_uuid',
                return_value=db_numa_topology):
            return claims.Claim(self.context, instance, self.tracker,
                                self.resources, overhead=overhead,
                                limits=limits)

    def _fake_instance(self, **kwargs):
        instance = {
            'uuid': str(uuid.uuid1()),
            'memory_mb': 1024,
            'root_gb': 10,
            'ephemeral_gb': 5,
            'vcpus': 1,
            'system_metadata': {},
            'numa_topology': None
        }
        instance.update(**kwargs)
        return fake_instance.fake_instance_obj(self.context, **instance)

    def _fake_instance_type(self, **kwargs):
        instance_type = {
            'id': 1,
            'name': 'fakeitype',
            'memory_mb': 1,
            'vcpus': 1,
            'root_gb': 1,
            'ephemeral_gb': 2
        }
        instance_type.update(**kwargs)
        return objects.Flavor(**instance_type)

    def _fake_resources(self, values=None):
        resources = {
            'memory_mb': 2048,
            'memory_mb_used': 0,
            'free_ram_mb': 2048,
            'local_gb': 20,
            'local_gb_used': 0,
            'free_disk_gb': 20,
            'vcpus': 2,
            'vcpus_used': 0,
            'numa_topology': objects.NUMATopology(
                cells=[objects.NUMACell(id=1, cpuset=set([1, 2]), memory=512,
                                        memory_usage=0, cpu_usage=0,
                                        mempages=[], siblings=[],
                                        pinned_cpus=set([])),
                       objects.NUMACell(id=2, cpuset=set([3, 4]), memory=512,
                                        memory_usage=0, cpu_usage=0,
                                        mempages=[], siblings=[],
                                        pinned_cpus=set([]))]
                )._to_json()
        }
        if values:
            resources.update(values)
        return resources

    def test_memory_unlimited(self, mock_get):
        self._claim(memory_mb=99999999)

    def test_disk_unlimited_root(self, mock_get):
        self._claim(root_gb=999999)

    def test_disk_unlimited_ephemeral(self, mock_get):
        self._claim(ephemeral_gb=999999)

    def test_memory_with_overhead(self, mock_get):
        overhead = {'memory_mb': 8}
        limits = {'memory_mb': 2048}
        self._claim(memory_mb=2040, limits=limits,
                    overhead=overhead)

    def test_memory_with_overhead_insufficient(self, mock_get):
        overhead = {'memory_mb': 9}
        limits = {'memory_mb': 2048}

        self.assertRaises(exception.ComputeResourcesUnavailable,
                          self._claim, limits=limits, overhead=overhead,
                          memory_mb=2040)

    def test_memory_oversubscription(self, mock_get):
        self._claim(memory_mb=4096)

    def test_memory_insufficient(self, mock_get):
        limits = {'memory_mb': 8192}
        self.assertRaises(exception.ComputeResourcesUnavailable,
                          self._claim, limits=limits, memory_mb=16384)

    def test_disk_oversubscription(self, mock_get):
        limits = {'disk_gb': 60}
        self._claim(root_gb=10, ephemeral_gb=40,
                    limits=limits)

    def test_disk_insufficient(self, mock_get):
        limits = {'disk_gb': 45}
        self.assertRaisesRegex(
                exception.ComputeResourcesUnavailable,
                "disk",
                self._claim, limits=limits, root_gb=10, ephemeral_gb=40)

    def test_disk_and_memory_insufficient(self, mock_get):
        limits = {'disk_gb': 45, 'memory_mb': 8192}
        self.assertRaisesRegex(
                exception.ComputeResourcesUnavailable,
                "memory.*disk",
                self._claim, limits=limits, root_gb=10, ephemeral_gb=40,
                memory_mb=16384)

    @pci_fakes.patch_pci_whitelist
    @mock.patch('nova.objects.InstancePCIRequests.get_by_instance')
    def test_pci_pass(self, mock_get_by_instance, mock_get):
        dev_dict = {
            'compute_node_id': 1,
            'address': 'a',
            'product_id': 'p',
            'vendor_id': 'v',
            'numa_node': 0,
            'status': 'available'}
        self.tracker.new_pci_tracker()
        self.tracker.pci_tracker._set_hvdevs([dev_dict])
        claim = self._claim()
        request = objects.InstancePCIRequest(count=1,
            spec=[{'vendor_id': 'v', 'product_id': 'p'}])
        requests = objects.InstancePCIRequests(requests=[request])
        mock_get.return_value = requests
        mock_get_by_instance.return_value = requests
        self.assertIsNone(claim._test_pci())

    @pci_fakes.patch_pci_whitelist
    @mock.patch('nova.objects.InstancePCIRequests.get_by_instance')
    def test_pci_fail(self, mock_get_by_instance, mock_get):
        dev_dict = {
            'compute_node_id': 1,
            'address': 'a',
            'product_id': 'p',
            'vendor_id': 'v1',
            'numa_node': 1,
            'status': 'available'}
        self.tracker.new_pci_tracker()
        self.tracker.pci_tracker._set_hvdevs([dev_dict])
        claim = self._claim()
        request = objects.InstancePCIRequest(count=1,
            spec=[{'vendor_id': 'v', 'product_id': 'p'}])
        requests = objects.InstancePCIRequests(requests=[request])
        mock_get.return_value = requests
        mock_get_by_instance.return_value = requests
        claim._test_pci()

    @pci_fakes.patch_pci_whitelist
    def test_pci_pass_no_requests(self, mock_get):
        dev_dict = {
            'compute_node_id': 1,
            'address': 'a',
            'product_id': 'p',
            'vendor_id': 'v',
            'numa_node': 0,
            'status': 'available'}
        self.tracker.new_pci_tracker()
        self.tracker.pci_tracker._set_hvdevs([dev_dict])
        claim = self._claim()
        self.assertIsNone(claim._test_pci())

    def test_ext_resources(self, mock_get):
        self._claim()
        self.assertTrue(self.tracker.ext_resources_handler.test_called)
        self.assertFalse(self.tracker.ext_resources_handler.usage_is_itype)

    def test_numa_topology_no_limit(self, mock_get):
        huge_instance = objects.InstanceNUMATopology(
                cells=[objects.InstanceNUMACell(
                    id=1, cpuset=set([1, 2]), memory=512)])
        self._claim(numa_topology=huge_instance)

    def test_numa_topology_fails(self, mock_get):
        huge_instance = objects.InstanceNUMATopology(
                cells=[objects.InstanceNUMACell(
                    id=1, cpuset=set([1, 2, 3, 4, 5]), memory=2048)])
        limit_topo = objects.NUMATopologyLimits(
            cpu_allocation_ratio=1, ram_allocation_ratio=1)
        self.assertRaises(exception.ComputeResourcesUnavailable,
                          self._claim,
                          limits={'numa_topology': limit_topo},
                          numa_topology=huge_instance)

    def test_numa_topology_passes(self, mock_get):
        huge_instance = objects.InstanceNUMATopology(
                cells=[objects.InstanceNUMACell(
                    id=1, cpuset=set([1, 2]), memory=512)])
        limit_topo = objects.NUMATopologyLimits(
            cpu_allocation_ratio=1, ram_allocation_ratio=1)
        self._claim(limits={'numa_topology': limit_topo},
                    numa_topology=huge_instance)

    @pci_fakes.patch_pci_whitelist
    @mock.patch('nova.objects.InstancePCIRequests.get_by_instance')
    def test_numa_topology_with_pci(self, mock_get_by_instance, mock_get):
        dev_dict = {
            'compute_node_id': 1,
            'address': 'a',
            'product_id': 'p',
            'vendor_id': 'v',
            'numa_node': 1,
            'status': 'available'}
        self.tracker.new_pci_tracker()
        self.tracker.pci_tracker._set_hvdevs([dev_dict])
        request = objects.InstancePCIRequest(count=1,
            spec=[{'vendor_id': 'v', 'product_id': 'p'}])
        requests = objects.InstancePCIRequests(requests=[request])
        mock_get.return_value = requests
        mock_get_by_instance.return_value = requests

        huge_instance = objects.InstanceNUMATopology(
                cells=[objects.InstanceNUMACell(
                    id=1, cpuset=set([1, 2]), memory=512)])

        self._claim(numa_topology=huge_instance)

    @pci_fakes.patch_pci_whitelist
    @mock.patch('nova.objects.InstancePCIRequests.get_by_instance')
    def test_numa_topology_with_pci_fail(self, mock_get_by_instance, mock_get):
        dev_dict = {
            'compute_node_id': 1,
            'address': 'a',
            'product_id': 'p',
            'vendor_id': 'v',
            'numa_node': 1,
            'status': 'available'}
        dev_dict2 = {
            'compute_node_id': 1,
            'address': 'a',
            'product_id': 'p',
            'vendor_id': 'v',
            'numa_node': 2,
            'status': 'available'}
        self.tracker.new_pci_tracker()
        self.tracker.pci_tracker._set_hvdevs([dev_dict, dev_dict2])

        request = objects.InstancePCIRequest(count=2,
            spec=[{'vendor_id': 'v', 'product_id': 'p'}])
        requests = objects.InstancePCIRequests(requests=[request])
        mock_get.return_value = requests
        mock_get_by_instance.return_value = requests

        huge_instance = objects.InstanceNUMATopology(
                cells=[objects.InstanceNUMACell(
                    id=1, cpuset=set([1, 2]), memory=512)])

        self.assertRaises(exception.ComputeResourcesUnavailable,
                          self._claim,
                          numa_topology=huge_instance)

    @pci_fakes.patch_pci_whitelist
    @mock.patch('nova.objects.InstancePCIRequests.get_by_instance')
    def test_numa_topology_with_pci_no_numa_info(self,
                                                 mock_get_by_instance,
                                                 mock_get):
        dev_dict = {
            'compute_node_id': 1,
            'address': 'a',
            'product_id': 'p',
            'vendor_id': 'v',
            'numa_node': None,
            'status': 'available'}
        self.tracker.new_pci_tracker()
        self.tracker.pci_tracker._set_hvdevs([dev_dict])

        request = objects.InstancePCIRequest(count=1,
            spec=[{'vendor_id': 'v', 'product_id': 'p'}])
        requests = objects.InstancePCIRequests(requests=[request])
        mock_get.return_value = requests
        mock_get_by_instance.return_value = requests

        huge_instance = objects.InstanceNUMATopology(
                cells=[objects.InstanceNUMACell(
                    id=1, cpuset=set([1, 2]), memory=512)])

        self._claim(numa_topology= huge_instance)

    def test_abort(self, mock_get):
        claim = self._abort()
        self.assertTrue(claim.tracker.icalled)

    def _abort(self):
        claim = None
        try:
            with self._claim(memory_mb=4096) as claim:
                raise test.TestingException("abort")
        except test.TestingException:
            pass

        return claim


class MoveClaimTestCase(ClaimTestCase):

    def setUp(self):
        super(MoveClaimTestCase, self).setUp()
        self.instance = self._fake_instance()
        self.get_numa_constraint_patch = None

    def _claim(self, limits=None, overhead=None, **kwargs):
        numa_constraint = kwargs.pop('numa_topology', None)
        instance_type = self._fake_instance_type(**kwargs)
        if overhead is None:
            overhead = {'memory_mb': 0}
        with mock.patch(
                'nova.virt.hardware.numa_get_constraints',
                return_value=numa_constraint):
            return claims.MoveClaim(self.context, self.instance, instance_type,
                                     {}, self.tracker, self.resources,
                                     overhead=overhead, limits=limits)

    def _set_pci_request(self, claim):
        request = [{'count': 1,
                       'spec': [{'vendor_id': 'v', 'product_id': 'p'}],
                      }]
        claim.instance.update(
            system_metadata={'new_pci_requests': jsonutils.dumps(request)})

    @mock.patch('nova.objects.InstancePCIRequests.get_by_instance_uuid',
                return_value=objects.InstancePCIRequests(requests=[]))
    def test_ext_resources(self, mock_get):
        self._claim()
        self.assertTrue(self.tracker.ext_resources_handler.test_called)
        self.assertTrue(self.tracker.ext_resources_handler.usage_is_itype)

    @mock.patch('nova.objects.InstancePCIRequests.get_by_instance_uuid',
                return_value=objects.InstancePCIRequests(requests=[]))
    def test_abort(self, mock_get):
        claim = self._abort()
        self.assertTrue(claim.tracker.rcalled)

    @mock.patch('nova.objects.InstancePCIRequests.get_by_instance_uuid',
                return_value=objects.InstancePCIRequests(requests=[]))
    def test_create_migration_context(self, mock_get):
        numa_topology = objects.InstanceNUMATopology(
                cells=[objects.InstanceNUMACell(
                    id=1, cpuset=set([1, 2]), memory=512)])
        self.instance.numa_topology = None
        claim = self._claim(numa_topology=numa_topology)
        migration = objects.Migration(context=self.context, id=42)
        claim.migration = migration
        fake_mig_context = mock.Mock(spec=objects.MigrationContext)
        with mock.patch('nova.objects.MigrationContext',
                        return_value=fake_mig_context) as ctxt_mock:
            claim.create_migration_context()
            ctxt_mock.assert_called_once_with(
                context=self.context, instance_uuid=self.instance.uuid,
                migration_id=42, old_numa_topology=None,
                new_numa_topology=mock.ANY)
            self.assertIsInstance(ctxt_mock.call_args[1]['new_numa_topology'],
                                  objects.InstanceNUMATopology)
            self.assertEqual(migration, claim.migration)
