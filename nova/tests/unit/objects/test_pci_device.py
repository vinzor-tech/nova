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

import copy

from oslo_utils import timeutils

from nova import context
from nova import db
from nova import exception
from nova.objects import fields
from nova.objects import instance
from nova.objects import pci_device
from nova.tests.unit.objects import test_objects

dev_dict = {
    'compute_node_id': 1,
    'address': 'a',
    'product_id': 'p',
    'vendor_id': 'v',
    'numa_node': 0,
    'status': fields.PciDeviceStatus.AVAILABLE}


fake_db_dev = {
    'created_at': None,
    'updated_at': None,
    'deleted_at': None,
    'deleted': None,
    'id': 1,
    'compute_node_id': 1,
    'address': 'a',
    'vendor_id': 'v',
    'product_id': 'p',
    'numa_node': 0,
    'dev_type': fields.PciDeviceType.STANDARD,
    'status': fields.PciDeviceStatus.AVAILABLE,
    'dev_id': 'i',
    'label': 'l',
    'instance_uuid': None,
    'extra_info': '{}',
    'request_id': None,
    }


fake_db_dev_1 = {
    'created_at': None,
    'updated_at': None,
    'deleted_at': None,
    'deleted': None,
    'id': 2,
    'compute_node_id': 1,
    'address': 'a1',
    'vendor_id': 'v1',
    'product_id': 'p1',
    'numa_node': 1,
    'dev_type': fields.PciDeviceType.STANDARD,
    'status': fields.PciDeviceStatus.AVAILABLE,
    'dev_id': 'i',
    'label': 'l',
    'instance_uuid': None,
    'extra_info': '{}',
    'request_id': None,
    }


class _TestPciDeviceObject(object):
    def _create_fake_instance(self):
        self.inst = instance.Instance()
        self.inst.uuid = 'fake-inst-uuid'
        self.inst.pci_devices = pci_device.PciDeviceList()

    def _create_fake_pci_device(self, ctxt=None):
        if not ctxt:
            ctxt = context.get_admin_context()
        self.mox.StubOutWithMock(db, 'pci_device_get_by_addr')
        db.pci_device_get_by_addr(ctxt, 1, 'a').AndReturn(fake_db_dev)
        self.mox.ReplayAll()
        self.pci_device = pci_device.PciDevice.get_by_dev_addr(ctxt, 1, 'a')

    def test_create_pci_device(self):
        self.pci_device = pci_device.PciDevice.create(dev_dict)
        self.assertEqual(self.pci_device.product_id, 'p')
        self.assertEqual(self.pci_device.obj_what_changed(),
                         set(['compute_node_id', 'product_id', 'vendor_id',
                              'numa_node', 'status', 'address', 'extra_info']))

    def test_pci_device_extra_info(self):
        self.dev_dict = copy.copy(dev_dict)
        self.dev_dict['k1'] = 'v1'
        self.dev_dict['k2'] = 'v2'
        self.pci_device = pci_device.PciDevice.create(self.dev_dict)
        extra_value = self.pci_device.extra_info
        self.assertEqual(extra_value.get('k1'), 'v1')
        self.assertEqual(set(extra_value.keys()), set(('k1', 'k2')))
        self.assertEqual(self.pci_device.obj_what_changed(),
                         set(['compute_node_id', 'address', 'product_id',
                              'vendor_id', 'numa_node', 'status',
                              'extra_info']))

    def test_update_device(self):
        self.pci_device = pci_device.PciDevice.create(dev_dict)
        self.pci_device.obj_reset_changes()
        changes = {'product_id': 'p2', 'vendor_id': 'v2'}
        self.pci_device.update_device(changes)
        self.assertEqual(self.pci_device.vendor_id, 'v2')
        self.assertEqual(self.pci_device.obj_what_changed(),
                         set(['vendor_id', 'product_id']))

    def test_update_device_same_value(self):
        self.pci_device = pci_device.PciDevice.create(dev_dict)
        self.pci_device.obj_reset_changes()
        changes = {'product_id': 'p', 'vendor_id': 'v2'}
        self.pci_device.update_device(changes)
        self.assertEqual(self.pci_device.product_id, 'p')
        self.assertEqual(self.pci_device.vendor_id, 'v2')
        self.assertEqual(self.pci_device.obj_what_changed(),
                         set(['vendor_id', 'product_id']))

    def test_get_by_dev_addr(self):
        ctxt = context.get_admin_context()
        self.mox.StubOutWithMock(db, 'pci_device_get_by_addr')
        db.pci_device_get_by_addr(ctxt, 1, 'a').AndReturn(fake_db_dev)
        self.mox.ReplayAll()
        self.pci_device = pci_device.PciDevice.get_by_dev_addr(ctxt, 1, 'a')
        self.assertEqual(self.pci_device.product_id, 'p')
        self.assertEqual(self.pci_device.obj_what_changed(), set())

    def test_get_by_dev_id(self):
        ctxt = context.get_admin_context()
        self.mox.StubOutWithMock(db, 'pci_device_get_by_id')
        db.pci_device_get_by_id(ctxt, 1).AndReturn(fake_db_dev)
        self.mox.ReplayAll()
        self.pci_device = pci_device.PciDevice.get_by_dev_id(ctxt, 1)
        self.assertEqual(self.pci_device.product_id, 'p')
        self.assertEqual(self.pci_device.obj_what_changed(), set())

    def test_save(self):
        ctxt = context.get_admin_context()
        self._create_fake_pci_device(ctxt=ctxt)
        return_dev = dict(fake_db_dev, status=fields.PciDeviceStatus.AVAILABLE,
                          instance_uuid='fake-uuid-3')
        self.pci_device.status = fields.PciDeviceStatus.ALLOCATED
        self.pci_device.instance_uuid = 'fake-uuid-2'
        expected_updates = dict(status=fields.PciDeviceStatus.ALLOCATED,
                                instance_uuid='fake-uuid-2')
        self.mox.StubOutWithMock(db, 'pci_device_update')
        db.pci_device_update(ctxt, 1, 'a',
                             expected_updates).AndReturn(return_dev)
        self.mox.ReplayAll()
        self.pci_device.save()
        self.assertEqual(self.pci_device.status,
                         fields.PciDeviceStatus.AVAILABLE)
        self.assertEqual(self.pci_device.instance_uuid,
                         'fake-uuid-3')

    def test_save_no_extra_info(self):
        return_dev = dict(fake_db_dev, status=fields.PciDeviceStatus.AVAILABLE,
                          instance_uuid='fake-uuid-3')

        def _fake_update(ctxt, node_id, addr, updates):
            self.extra_info = updates.get('extra_info')
            return return_dev

        ctxt = context.get_admin_context()
        self.stubs.Set(db, 'pci_device_update', _fake_update)
        self.pci_device = pci_device.PciDevice.create(dev_dict)
        self.pci_device._context = ctxt
        self.pci_device.save()
        self.assertEqual(self.extra_info, '{}')

    def test_save_removed(self):
        ctxt = context.get_admin_context()
        self._create_fake_pci_device(ctxt=ctxt)
        self.pci_device.status = fields.PciDeviceStatus.REMOVED
        self.mox.StubOutWithMock(db, 'pci_device_destroy')
        db.pci_device_destroy(ctxt, 1, 'a')
        self.mox.ReplayAll()
        self.pci_device.save()
        self.assertEqual(self.pci_device.status,
                         fields.PciDeviceStatus.DELETED)

    def test_save_deleted(self):
        def _fake_destroy(ctxt, node_id, addr):
            self.called = True

        def _fake_update(ctxt, node_id, addr, updates):
            self.called = True
        self.stubs.Set(db, 'pci_device_destroy', _fake_destroy)
        self.stubs.Set(db, 'pci_device_update', _fake_update)
        self._create_fake_pci_device()
        self.pci_device.status = fields.PciDeviceStatus.DELETED
        self.called = False
        self.pci_device.save()
        self.assertEqual(self.called, False)

    def test_update_numa_node(self):
        self.pci_device = pci_device.PciDevice.create(dev_dict)
        self.assertEqual(0, self.pci_device.numa_node)

        self.dev_dict = copy.copy(dev_dict)
        self.dev_dict['numa_node'] = '1'
        self.pci_device = pci_device.PciDevice.create(self.dev_dict)
        self.assertEqual(1, self.pci_device.numa_node)

    def test_pci_device_equivalent(self):
        pci_device1 = pci_device.PciDevice.create(dev_dict)
        pci_device2 = pci_device.PciDevice.create(dev_dict)
        self.assertEqual(pci_device1, pci_device2)

    def test_pci_device_equivalent_with_ignore_field(self):
        pci_device1 = pci_device.PciDevice.create(dev_dict)
        pci_device2 = pci_device.PciDevice.create(dev_dict)
        pci_device2.updated_at = timeutils.utcnow()
        self.assertEqual(pci_device1, pci_device2)

    def test_pci_device_not_equivalent1(self):
        pci_device1 = pci_device.PciDevice.create(dev_dict)
        dev_dict2 = copy.copy(dev_dict)
        dev_dict2['address'] = 'b'
        pci_device2 = pci_device.PciDevice.create(dev_dict2)
        self.assertNotEqual(pci_device1, pci_device2)

    def test_pci_device_not_equivalent2(self):
        pci_device1 = pci_device.PciDevice.create(dev_dict)
        pci_device2 = pci_device.PciDevice.create(dev_dict)
        delattr(pci_device2, 'address')
        self.assertNotEqual(pci_device1, pci_device2)

    def test_pci_device_not_equivalent_with_none(self):
        pci_device1 = pci_device.PciDevice.create(dev_dict)
        pci_device2 = pci_device.PciDevice.create(dev_dict)
        pci_device1.instance_uuid = 'aaa'
        pci_device2.instance_uuid = None
        self.assertNotEqual(pci_device1, pci_device2)

    def test_claim_device(self):
        self._create_fake_instance()
        devobj = pci_device.PciDevice.create(dev_dict)
        devobj.claim(self.inst)
        self.assertEqual(devobj.status,
                         fields.PciDeviceStatus.CLAIMED)
        self.assertEqual(devobj.instance_uuid,
                         self.inst.uuid)
        self.assertEqual(len(self.inst.pci_devices), 0)

    def test_claim_device_fail(self):
        self._create_fake_instance()
        devobj = pci_device.PciDevice.create(dev_dict)
        devobj.status = fields.PciDeviceStatus.ALLOCATED
        self.assertRaises(exception.PciDeviceInvalidStatus,
                          devobj.claim, self.inst)

    def test_allocate_device(self):
        self._create_fake_instance()
        devobj = pci_device.PciDevice.create(dev_dict)
        devobj.claim(self.inst)
        devobj.allocate(self.inst)
        self.assertEqual(devobj.status,
                         fields.PciDeviceStatus.ALLOCATED)
        self.assertEqual(devobj.instance_uuid, 'fake-inst-uuid')
        self.assertEqual(len(self.inst.pci_devices), 1)
        self.assertEqual(self.inst.pci_devices[0].vendor_id,
                         'v')
        self.assertEqual(self.inst.pci_devices[0].status,
                         fields.PciDeviceStatus.ALLOCATED)

    def test_allocate_device_fail_status(self):
        self._create_fake_instance()
        devobj = pci_device.PciDevice.create(dev_dict)
        devobj.status = 'removed'
        self.assertRaises(exception.PciDeviceInvalidStatus,
                          devobj.allocate, self.inst)

    def test_allocate_device_fail_owner(self):
        self._create_fake_instance()
        inst_2 = instance.Instance()
        inst_2.uuid = 'fake-inst-uuid-2'
        devobj = pci_device.PciDevice.create(dev_dict)
        devobj.claim(self.inst)
        self.assertRaises(exception.PciDeviceInvalidOwner,
                          devobj.allocate, inst_2)

    def test_free_claimed_device(self):
        self._create_fake_instance()
        devobj = pci_device.PciDevice.create(dev_dict)
        devobj.claim(self.inst)
        devobj.free(self.inst)
        self.assertEqual(devobj.status,
                         fields.PciDeviceStatus.AVAILABLE)
        self.assertIsNone(devobj.instance_uuid)

    def test_free_allocated_device(self):
        self._create_fake_instance()
        ctx = context.get_admin_context()
        devobj = pci_device.PciDevice._from_db_object(
                ctx, pci_device.PciDevice(), fake_db_dev)
        devobj.claim(self.inst)
        devobj.allocate(self.inst)
        self.assertEqual(len(self.inst.pci_devices), 1)
        devobj.free(self.inst)
        self.assertEqual(len(self.inst.pci_devices), 0)
        self.assertEqual(devobj.status,
                         fields.PciDeviceStatus.AVAILABLE)
        self.assertIsNone(devobj.instance_uuid)

    def test_free_device_fail(self):
        self._create_fake_instance()
        devobj = pci_device.PciDevice.create(dev_dict)
        devobj.status = fields.PciDeviceStatus.REMOVED
        self.assertRaises(exception.PciDeviceInvalidStatus, devobj.free)

    def test_remove_device(self):
        self._create_fake_instance()
        devobj = pci_device.PciDevice.create(dev_dict)
        devobj.remove()
        self.assertEqual(devobj.status, fields.PciDeviceStatus.REMOVED)
        self.assertIsNone(devobj.instance_uuid)

    def test_remove_device_fail(self):
        self._create_fake_instance()
        devobj = pci_device.PciDevice.create(dev_dict)
        devobj.claim(self.inst)
        self.assertRaises(exception.PciDeviceInvalidStatus, devobj.remove)


class TestPciDeviceObject(test_objects._LocalTest,
                          _TestPciDeviceObject):
    pass


class TestPciDeviceObjectRemote(test_objects._RemoteTest,
                                _TestPciDeviceObject):
    pass


fake_pci_devs = [fake_db_dev, fake_db_dev_1]


class _TestPciDeviceListObject(object):
    def test_get_by_compute_node(self):
        ctxt = context.get_admin_context()
        self.mox.StubOutWithMock(db, 'pci_device_get_all_by_node')
        db.pci_device_get_all_by_node(ctxt, 1).AndReturn(fake_pci_devs)
        self.mox.ReplayAll()
        devs = pci_device.PciDeviceList.get_by_compute_node(ctxt, 1)
        for i in range(len(fake_pci_devs)):
            self.assertIsInstance(devs[i], pci_device.PciDevice)
            self.assertEqual(fake_pci_devs[i]['vendor_id'], devs[i].vendor_id)

    def test_get_by_instance_uuid(self):
        ctxt = context.get_admin_context()
        fake_db_1 = dict(fake_db_dev, address='a1',
                         status=fields.PciDeviceStatus.ALLOCATED,
                         instance_uuid='1')
        fake_db_2 = dict(fake_db_dev, address='a2',
                         status=fields.PciDeviceStatus.ALLOCATED,
                         instance_uuid='1')
        self.mox.StubOutWithMock(db, 'pci_device_get_all_by_instance_uuid')
        db.pci_device_get_all_by_instance_uuid(ctxt, '1').AndReturn(
            [fake_db_1, fake_db_2])
        self.mox.ReplayAll()
        devs = pci_device.PciDeviceList.get_by_instance_uuid(ctxt, '1')
        self.assertEqual(len(devs), 2)
        for i in range(len(fake_pci_devs)):
            self.assertIsInstance(devs[i], pci_device.PciDevice)
        self.assertEqual(devs[0].vendor_id, 'v')
        self.assertEqual(devs[1].vendor_id, 'v')


class TestPciDeviceListObject(test_objects._LocalTest,
                                  _TestPciDeviceListObject):
    pass


class TestPciDeviceListObjectRemote(test_objects._RemoteTest,
                              _TestPciDeviceListObject):
    pass
