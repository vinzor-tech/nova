#    Copyright 2013 IBM Corp.
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

import contextlib

import mock
from oslo_vmware import exceptions as oslo_vmw_exceptions
from oslo_vmware import vim_util as vutil

from nova.compute import vm_states
from nova import context
from nova import exception
from nova import test
from nova.tests.unit import fake_instance
from nova.tests.unit.image import fake as image_fake
from nova.tests.unit.virt.vmwareapi import fake as vmwareapi_fake
from nova.tests.unit.virt.vmwareapi import stubs
from nova.virt.vmwareapi import constants
from nova.virt.vmwareapi import driver
from nova.virt.vmwareapi import vm_util
from nova.virt.vmwareapi import volumeops


class VMwareVolumeOpsTestCase(test.NoDBTestCase):

    def setUp(self):

        super(VMwareVolumeOpsTestCase, self).setUp()
        vmwareapi_fake.reset()
        stubs.set_stubs(self.stubs)
        self._session = driver.VMwareAPISession()
        self._context = context.RequestContext('fake_user', 'fake_project')

        self._volumeops = volumeops.VMwareVolumeOps(self._session)
        self._image_id = image_fake.get_valid_image_id()
        self._instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
            'vcpus': 1,
            'memory_mb': 512,
            'image_ref': self._image_id,
            'root_gb': 10,
            'node': 'respool-1001(MyResPoolName)',
            'expected_attrs': ['system_metadata'],
        }
        self._instance = fake_instance.fake_instance_obj(self._context,
            **self._instance_values)

    def _test_detach_disk_from_vm(self, destroy_disk=False):
        def fake_call_method(module, method, *args, **kwargs):
            vmdk_detach_config_spec = kwargs.get('spec')
            virtual_device_config = vmdk_detach_config_spec.deviceChange[0]
            self.assertEqual('remove', virtual_device_config.operation)
            self.assertEqual('ns0:VirtualDeviceConfigSpec',
                              virtual_device_config.obj_name)
            if destroy_disk:
                self.assertEqual('destroy',
                                 virtual_device_config.fileOperation)
            else:
                self.assertFalse(hasattr(virtual_device_config,
                                 'fileOperation'))
            return 'fake_configure_task'
        with contextlib.nested(
            mock.patch.object(self._session, '_wait_for_task'),
            mock.patch.object(self._session, '_call_method',
                              fake_call_method)
        ) as (_wait_for_task, _call_method):
            fake_device = vmwareapi_fake.DataObject()
            fake_device.backing = vmwareapi_fake.DataObject()
            fake_device.backing.fileName = 'fake_path'
            fake_device.key = 'fake_key'
            self._volumeops.detach_disk_from_vm('fake_vm_ref', self._instance,
                                                fake_device, destroy_disk)
            _wait_for_task.assert_has_calls([
                   mock.call('fake_configure_task')])

    def test_detach_with_destroy_disk_from_vm(self):
        self._test_detach_disk_from_vm(destroy_disk=True)

    def test_detach_without_destroy_disk_from_vm(self):
        self._test_detach_disk_from_vm(destroy_disk=False)

    def _fake_call_get_object_property(self, uuid, result):
        def fake_call_method(vim, method, vm_ref, prop):
            expected_prop = 'config.extraConfig["volume-%s"]' % uuid
            self.assertEqual('VirtualMachine', vm_ref._type)
            self.assertEqual(expected_prop, prop)
            return result
        return fake_call_method

    def test_get_volume_uuid(self):
        vm_ref = vmwareapi_fake.ManagedObjectReference('VirtualMachine',
                                                       'vm-134')
        uuid = '1234'
        opt_val = vmwareapi_fake.OptionValue('volume-%s' % uuid, 'volume-val')
        fake_call = self._fake_call_get_object_property(uuid, opt_val)
        with mock.patch.object(self._session, "_call_method", fake_call):
            val = self._volumeops._get_volume_uuid(vm_ref, uuid)
            self.assertEqual('volume-val', val)

    def test_get_volume_uuid_not_found(self):
        vm_ref = vmwareapi_fake.ManagedObjectReference('VirtualMachine',
                                                       'vm-134')
        uuid = '1234'
        fake_call = self._fake_call_get_object_property(uuid, None)
        with mock.patch.object(self._session, "_call_method", fake_call):
            val = self._volumeops._get_volume_uuid(vm_ref, uuid)
            self.assertIsNone(val)

    def test_attach_volume_vmdk_invalid(self):
        connection_info = {'driver_volume_type': 'vmdk',
                           'serial': 'volume-fake-id',
                           'data': {'volume': 'vm-10',
                                    'volume_id': 'volume-fake-id'}}
        instance = mock.MagicMock(name='fake-name', vm_state=vm_states.ACTIVE)
        vmdk_info = vm_util.VmdkInfo('fake-path', constants.ADAPTER_TYPE_IDE,
                                     constants.DISK_TYPE_PREALLOCATED, 1024,
                                     'fake-device')
        with contextlib.nested(
            mock.patch.object(vm_util, 'get_vm_ref'),
            mock.patch.object(self._volumeops, '_get_volume_ref'),
            mock.patch.object(vm_util, 'get_vmdk_info',
                              return_value=vmdk_info)
        ) as (get_vm_ref, get_volume_ref, get_vmdk_info):
            self.assertRaises(exception.Invalid,
                self._volumeops._attach_volume_vmdk, connection_info,
                instance)

            get_vm_ref.assert_called_once_with(self._volumeops._session,
                                               instance)
            get_volume_ref.assert_called_once_with(
                connection_info['data']['volume'])
            self.assertTrue(get_vmdk_info.called)

    @mock.patch.object(vm_util, 'get_vm_extra_config_spec',
                       return_value=mock.sentinel.extra_config)
    @mock.patch.object(vm_util, 'reconfigure_vm')
    def test_update_volume_details(self, reconfigure_vm,
                                   get_vm_extra_config_spec):
            volume_uuid = '26f5948e-52a3-4ee6-8d48-0a379afd0828'
            device_uuid = '0d86246a-2adb-470d-a9f7-bce09930c5d'
            self._volumeops._update_volume_details(
                mock.sentinel.vm_ref, volume_uuid, device_uuid)

            get_vm_extra_config_spec.assert_called_once_with(
                self._volumeops._session.vim.client.factory,
                {'volume-%s' % volume_uuid: device_uuid})
            reconfigure_vm.assert_called_once_with(self._volumeops._session,
                                                   mock.sentinel.vm_ref,
                                                   mock.sentinel.extra_config)

    def test_detach_volume_vmdk(self):

        vmdk_info = vm_util.VmdkInfo('fake-path', 'lsiLogic', 'thin',
                                     1024, 'fake-device')
        with contextlib.nested(
            mock.patch.object(vm_util, 'get_vm_ref',
                              return_value=mock.sentinel.vm_ref),
            mock.patch.object(self._volumeops, '_get_volume_ref',
                              return_value=mock.sentinel.volume_ref),
            mock.patch.object(self._volumeops,
                              '_get_vmdk_backed_disk_device',
                              return_value=mock.sentinel.device),
            mock.patch.object(vm_util, 'get_vmdk_info',
                              return_value=vmdk_info),
            mock.patch.object(self._volumeops, '_consolidate_vmdk_volume'),
            mock.patch.object(self._volumeops, 'detach_disk_from_vm'),
            mock.patch.object(self._volumeops, '_update_volume_details'),
        ) as (get_vm_ref, get_volume_ref, get_vmdk_backed_disk_device,
              get_vmdk_info, consolidate_vmdk_volume, detach_disk_from_vm,
              update_volume_details):

            connection_info = {'driver_volume_type': 'vmdk',
                               'serial': 'volume-fake-id',
                               'data': {'volume': 'vm-10',
                                        'volume_id':
                                        'd11a82de-ddaa-448d-b50a-a255a7e61a1e'
                                        }}
            instance = mock.MagicMock(name='fake-name',
                                      vm_state=vm_states.ACTIVE)
            self._volumeops._detach_volume_vmdk(connection_info, instance)

            get_vm_ref.assert_called_once_with(self._volumeops._session,
                                               instance)
            get_volume_ref.assert_called_once_with(
                connection_info['data']['volume'])
            get_vmdk_backed_disk_device.assert_called_once_with(
                mock.sentinel.vm_ref, connection_info['data'])
            get_vmdk_info.assert_called_once_with(self._volumeops._session,
                                                  mock.sentinel.volume_ref)
            consolidate_vmdk_volume.assert_called_once_with(
                instance, mock.sentinel.vm_ref, mock.sentinel.device,
                mock.sentinel.volume_ref, adapter_type=vmdk_info.adapter_type,
                disk_type=vmdk_info.disk_type)
            detach_disk_from_vm.assert_called_once_with(mock.sentinel.vm_ref,
                                                        instance,
                                                        mock.sentinel.device)
            update_volume_details.assert_called_once_with(
                mock.sentinel.vm_ref, connection_info['data']['volume_id'], "")

    def test_detach_volume_vmdk_invalid(self):
        connection_info = {'driver_volume_type': 'vmdk',
                           'serial': 'volume-fake-id',
                           'data': {'volume': 'vm-10',
                                    'volume_id': 'volume-fake-id'}}
        instance = mock.MagicMock(name='fake-name', vm_state=vm_states.ACTIVE)
        vmdk_info = vm_util.VmdkInfo('fake-path', constants.ADAPTER_TYPE_IDE,
                                     constants.DISK_TYPE_PREALLOCATED, 1024,
                                     'fake-device')
        with contextlib.nested(
            mock.patch.object(vm_util, 'get_vm_ref',
                              return_value=mock.sentinel.vm_ref),
            mock.patch.object(self._volumeops, '_get_volume_ref'),
            mock.patch.object(self._volumeops,
                              '_get_vmdk_backed_disk_device'),
            mock.patch.object(vm_util, 'get_vmdk_info',
                              return_value=vmdk_info)
        ) as (get_vm_ref, get_volume_ref, get_vmdk_backed_disk_device,
              get_vmdk_info):
            self.assertRaises(exception.Invalid,
                self._volumeops._detach_volume_vmdk, connection_info,
                instance)

            get_vm_ref.assert_called_once_with(self._volumeops._session,
                                               instance)
            get_volume_ref.assert_called_once_with(
                connection_info['data']['volume'])
            get_vmdk_backed_disk_device.assert_called_once_with(
                mock.sentinel.vm_ref, connection_info['data'])
            self.assertTrue(get_vmdk_info.called)

    def _test_attach_volume_vmdk(self, adapter_type=None):
        connection_info = {'driver_volume_type': constants.DISK_FORMAT_VMDK,
                           'serial': 'volume-fake-id',
                           'data': {'volume': 'vm-10',
                                    'volume_id': 'volume-fake-id'}}
        vm_ref = 'fake-vm-ref'
        volume_device = mock.MagicMock()
        volume_device.backing.fileName = 'fake-path'
        default_adapter_type = constants.DEFAULT_ADAPTER_TYPE
        disk_type = constants.DEFAULT_DISK_TYPE
        disk_uuid = 'e97f357b-331e-4ad1-b726-89be048fb811'
        backing = mock.Mock(uuid=disk_uuid)
        device = mock.Mock(backing=backing)
        vmdk_info = vm_util.VmdkInfo('fake-path', default_adapter_type,
                                     disk_type, 1024,
                                     device)
        adapter_type = adapter_type or default_adapter_type

        with contextlib.nested(
            mock.patch.object(vm_util, 'get_vm_ref', return_value=vm_ref),
            mock.patch.object(self._volumeops, '_get_volume_ref'),
            mock.patch.object(vm_util, 'get_vmdk_info',
                              return_value=vmdk_info),
            mock.patch.object(self._volumeops, 'attach_disk_to_vm'),
            mock.patch.object(self._volumeops, '_update_volume_details')
        ) as (get_vm_ref, get_volume_ref, get_vmdk_info, attach_disk_to_vm,
              update_volume_details):
            self._volumeops.attach_volume(connection_info, self._instance,
                                          adapter_type)

            get_vm_ref.assert_called_once_with(self._volumeops._session,
                                               self._instance)
            get_volume_ref.assert_called_once_with(
                connection_info['data']['volume'])
            self.assertTrue(get_vmdk_info.called)
            attach_disk_to_vm.assert_called_once_with(
                vm_ref, self._instance, adapter_type,
                constants.DISK_TYPE_PREALLOCATED, vmdk_path='fake-path')
            update_volume_details.assert_called_once_with(
                vm_ref, connection_info['data']['volume_id'], disk_uuid)

    def _test_attach_volume_iscsi(self, adapter_type=None):
        connection_info = {'driver_volume_type': 'iscsi',
                           'serial': 'volume-fake-id',
                           'data': {'volume': 'vm-10',
                                    'volume_id': 'volume-fake-id'}}
        vm_ref = 'fake-vm-ref'
        default_adapter_type = constants.DEFAULT_ADAPTER_TYPE
        adapter_type = adapter_type or default_adapter_type

        with contextlib.nested(
            mock.patch.object(vm_util, 'get_vm_ref', return_value=vm_ref),
            mock.patch.object(self._volumeops, '_iscsi_discover_target',
                              return_value=(mock.sentinel.device_name,
                                            mock.sentinel.uuid)),
            mock.patch.object(vm_util, 'get_scsi_adapter_type',
                              return_value=adapter_type),
            mock.patch.object(self._volumeops, 'attach_disk_to_vm')
        ) as (get_vm_ref, iscsi_discover_target, get_scsi_adapter_type,
              attach_disk_to_vm):
            self._volumeops.attach_volume(connection_info, self._instance,
                                          adapter_type)

            get_vm_ref.assert_called_once_with(self._volumeops._session,
                                               self._instance)
            iscsi_discover_target.assert_called_once_with(
                connection_info['data'])
            if adapter_type is None:
                self.assertTrue(get_scsi_adapter_type.called)
            attach_disk_to_vm.assert_called_once_with(vm_ref,
                self._instance, adapter_type, 'rdmp',
                device_name=mock.sentinel.device_name)

    def test_attach_volume_vmdk(self):
        for adapter_type in (None, constants.DEFAULT_ADAPTER_TYPE,
                             constants.ADAPTER_TYPE_BUSLOGIC,
                             constants.ADAPTER_TYPE_IDE,
                             constants.ADAPTER_TYPE_LSILOGICSAS,
                             constants.ADAPTER_TYPE_PARAVIRTUAL):
            self._test_attach_volume_vmdk(adapter_type)

    def test_attach_volume_iscsi(self):
        for adapter_type in (None, constants.DEFAULT_ADAPTER_TYPE,
                             constants.ADAPTER_TYPE_BUSLOGIC,
                             constants.ADAPTER_TYPE_LSILOGICSAS,
                             constants.ADAPTER_TYPE_PARAVIRTUAL):
            self._test_attach_volume_iscsi(adapter_type)

    @mock.patch.object(volumeops.VMwareVolumeOps,
                       '_get_vmdk_base_volume_device')
    @mock.patch.object(volumeops.VMwareVolumeOps, '_relocate_vmdk_volume')
    def test_consolidate_vmdk_volume_with_no_relocate(
            self, relocate_vmdk_volume, get_vmdk_base_volume_device):
        file_name = mock.sentinel.file_name
        backing = mock.Mock(fileName=file_name)
        original_device = mock.Mock(backing=backing)
        get_vmdk_base_volume_device.return_value = original_device

        device = mock.Mock(backing=backing)

        volume_ref = mock.sentinel.volume_ref
        vm_ref = mock.sentinel.vm_ref

        self._volumeops._consolidate_vmdk_volume(self._instance, vm_ref,
                                                 device, volume_ref)

        get_vmdk_base_volume_device.assert_called_once_with(volume_ref)
        self.assertFalse(relocate_vmdk_volume.called)

    @mock.patch.object(volumeops.VMwareVolumeOps,
                       '_get_vmdk_base_volume_device')
    @mock.patch.object(volumeops.VMwareVolumeOps, '_relocate_vmdk_volume')
    @mock.patch.object(volumeops.VMwareVolumeOps, '_get_host_of_vm')
    @mock.patch.object(volumeops.VMwareVolumeOps, '_get_res_pool_of_host')
    @mock.patch.object(volumeops.VMwareVolumeOps, 'detach_disk_from_vm')
    @mock.patch.object(volumeops.VMwareVolumeOps, 'attach_disk_to_vm')
    def test_consolidate_vmdk_volume_with_relocate(
            self, attach_disk_to_vm, detach_disk_from_vm, get_res_pool_of_host,
            get_host_of_vm, relocate_vmdk_volume, get_vmdk_base_volume_device):
        file_name = mock.sentinel.file_name
        backing = mock.Mock(fileName=file_name)
        original_device = mock.Mock(backing=backing)
        get_vmdk_base_volume_device.return_value = original_device

        new_file_name = mock.sentinel.new_file_name
        datastore = mock.sentinel.datastore
        new_backing = mock.Mock(fileName=new_file_name, datastore=datastore)
        device = mock.Mock(backing=new_backing)

        host = mock.sentinel.host
        get_host_of_vm.return_value = host
        rp = mock.sentinel.rp
        get_res_pool_of_host.return_value = rp

        instance = self._instance
        volume_ref = mock.sentinel.volume_ref
        vm_ref = mock.sentinel.vm_ref
        adapter_type = constants.ADAPTER_TYPE_BUSLOGIC
        disk_type = constants.DISK_TYPE_EAGER_ZEROED_THICK

        self._volumeops._consolidate_vmdk_volume(instance, vm_ref, device,
                                                 volume_ref, adapter_type,
                                                 disk_type)

        get_vmdk_base_volume_device.assert_called_once_with(volume_ref)
        relocate_vmdk_volume.assert_called_once_with(
            volume_ref, rp, datastore, host)
        detach_disk_from_vm.assert_called_once_with(
            volume_ref, instance, original_device, destroy_disk=True)
        attach_disk_to_vm.assert_called_once_with(
            volume_ref, instance, adapter_type, disk_type,
            vmdk_path=new_file_name)

    @mock.patch.object(volumeops.VMwareVolumeOps,
                       '_get_vmdk_base_volume_device')
    @mock.patch.object(volumeops.VMwareVolumeOps, '_relocate_vmdk_volume')
    @mock.patch.object(volumeops.VMwareVolumeOps, '_get_host_of_vm')
    @mock.patch.object(volumeops.VMwareVolumeOps, '_get_res_pool_of_host')
    @mock.patch.object(volumeops.VMwareVolumeOps, 'detach_disk_from_vm')
    @mock.patch.object(volumeops.VMwareVolumeOps, 'attach_disk_to_vm')
    def test_consolidate_vmdk_volume_with_missing_vmdk(
            self, attach_disk_to_vm, detach_disk_from_vm, get_res_pool_of_host,
            get_host_of_vm, relocate_vmdk_volume, get_vmdk_base_volume_device):
        file_name = mock.sentinel.file_name
        backing = mock.Mock(fileName=file_name)
        original_device = mock.Mock(backing=backing)
        get_vmdk_base_volume_device.return_value = original_device

        new_file_name = mock.sentinel.new_file_name
        datastore = mock.sentinel.datastore
        new_backing = mock.Mock(fileName=new_file_name, datastore=datastore)
        device = mock.Mock(backing=new_backing)

        host = mock.sentinel.host
        get_host_of_vm.return_value = host
        rp = mock.sentinel.rp
        get_res_pool_of_host.return_value = rp

        relocate_vmdk_volume.side_effect = [
            oslo_vmw_exceptions.FileNotFoundException, None]

        instance = mock.sentinel.instance
        volume_ref = mock.sentinel.volume_ref
        vm_ref = mock.sentinel.vm_ref
        adapter_type = constants.ADAPTER_TYPE_BUSLOGIC
        disk_type = constants.DISK_TYPE_EAGER_ZEROED_THICK

        self._volumeops._consolidate_vmdk_volume(instance, vm_ref, device,
                                                 volume_ref, adapter_type,
                                                 disk_type)

        get_vmdk_base_volume_device.assert_called_once_with(volume_ref)

        relocate_calls = [mock.call(volume_ref, rp, datastore, host),
                          mock.call(volume_ref, rp, datastore, host)]
        self.assertEqual(relocate_calls, relocate_vmdk_volume.call_args_list)
        detach_disk_from_vm.assert_called_once_with(
            volume_ref, instance, original_device)
        attach_disk_to_vm.assert_called_once_with(
            volume_ref, instance, adapter_type, disk_type,
            vmdk_path=new_file_name)

    def test_iscsi_get_host_iqn(self):
        host_mor = mock.Mock()
        iqn = 'iscsi-name'
        hba = vmwareapi_fake.HostInternetScsiHba(iqn)
        hbas = mock.MagicMock(HostHostBusAdapter=[hba])

        with contextlib.nested(
            mock.patch.object(vm_util, 'get_host_ref_for_vm',
                              return_value=host_mor),
            mock.patch.object(self._volumeops._session, '_call_method',
                              return_value=hbas)
        ) as (fake_get_host_ref_for_vm, fake_call_method):
            result = self._volumeops._iscsi_get_host_iqn(self._instance)

            fake_get_host_ref_for_vm.assert_called_once_with(
                            self._volumeops._session, self._instance)
            fake_call_method.assert_called_once_with(vutil,
                                    "get_object_property",
                                    host_mor,
                                    "config.storageDevice.hostBusAdapter")

            self.assertEqual(iqn, result)

    def test_iscsi_get_host_iqn_instance_not_found(self):
        host_mor = mock.Mock()
        iqn = 'iscsi-name'
        hba = vmwareapi_fake.HostInternetScsiHba(iqn)
        hbas = mock.MagicMock(HostHostBusAdapter=[hba])

        with contextlib.nested(
            mock.patch.object(vm_util, 'get_host_ref_for_vm',
                              side_effect=exception.InstanceNotFound('fake')),
            mock.patch.object(vm_util, 'get_host_ref',
                              return_value=host_mor),
            mock.patch.object(self._volumeops._session, '_call_method',
                              return_value=hbas)
        ) as (fake_get_host_ref_for_vm,
              fake_get_host_ref,
              fake_call_method):
            result = self._volumeops._iscsi_get_host_iqn(self._instance)

            fake_get_host_ref_for_vm.assert_called_once_with(
                        self._volumeops._session, self._instance)
            fake_get_host_ref.assert_called_once_with(
                        self._volumeops._session, self._volumeops._cluster)
            fake_call_method.assert_called_once_with(vutil,
                                    "get_object_property",
                                    host_mor,
                                    "config.storageDevice.hostBusAdapter")

            self.assertEqual(iqn, result)

    def test_get_volume_connector(self):
        vm_id = 'fake-vm'
        vm_ref = mock.MagicMock(value=vm_id)
        iqn = 'iscsi-name'
        url = 'test_url'
        self.flags(host_ip=url, group='vmware')

        with contextlib.nested(
            mock.patch.object(vm_util, 'get_vm_ref', return_value=vm_ref),
            mock.patch.object(self._volumeops, '_iscsi_get_host_iqn',
                              return_value=iqn)
        ) as (fake_get_vm_ref, fake_iscsi_get_host_iqn):
            connector = self._volumeops.get_volume_connector(self._instance)

            fake_get_vm_ref.assert_called_once_with(self._volumeops._session,
                                                    self._instance)
            fake_iscsi_get_host_iqn.assert_called_once_with(self._instance)

            self.assertEqual(url, connector['ip'])
            self.assertEqual(url, connector['host'])
            self.assertEqual(iqn, connector['initiator'])
            self.assertEqual(vm_id, connector['instance'])
