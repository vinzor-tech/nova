# Copyright (C) 2011 Midokura KK
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

import webob

from nova.api.openstack import api_version_request
from nova.api.openstack.compute.legacy_v2.contrib import virtual_interfaces \
        as vi20
from nova.api.openstack.compute import virtual_interfaces as vi21
from nova import compute
from nova.compute import api as compute_api
from nova import context
from nova import exception
from nova import network
from nova.objects import virtual_interface as vif_obj
from nova import test
from nova.tests.unit.api.openstack import fakes


FAKE_UUID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'


def compute_api_get(self, context, instance_id, expected_attrs=None,
                    want_objects=False):
    return dict(uuid=FAKE_UUID, id=instance_id, instance_type_id=1, host='bob')


def _generate_fake_vifs(context):
    vif = vif_obj.VirtualInterface(context=context)
    vif.address = '00-00-00-00-00-00'
    vif.network_id = 123
    vif.net_uuid = '22222222-2222-2222-2222-22222222222222222'
    vif.uuid = '00000000-0000-0000-0000-00000000000000000'
    fake_vifs = [vif]
    vif = vif_obj.VirtualInterface(context=context)
    vif.address = '11-11-11-11-11-11'
    vif.network_id = 456
    vif.net_uuid = '33333333-3333-3333-3333-33333333333333333'
    vif.uuid = '11111111-1111-1111-1111-11111111111111111'
    fake_vifs.append(vif)
    return fake_vifs


def get_vifs_by_instance(self, context, instance_id):
    return _generate_fake_vifs(context)


class FakeRequest(object):
    def __init__(self, context):
        self.environ = {'nova.context': context}


class ServerVirtualInterfaceTestV21(test.NoDBTestCase):
    wsgi_api_version = None
    expected_response = {
        'virtual_interfaces': [
            {'id': '00000000-0000-0000-0000-00000000000000000',
                'mac_address': '00-00-00-00-00-00'},
            {'id': '11111111-1111-1111-1111-11111111111111111',
                'mac_address': '11-11-11-11-11-11'}]}

    def setUp(self):
        super(ServerVirtualInterfaceTestV21, self).setUp()
        self.stubs.Set(compute.api.API, "get",
                       compute_api_get)
        self.stubs.Set(network.api.API, "get_vifs_by_instance",
                       get_vifs_by_instance)
        self._set_controller()

    def _set_controller(self):
        self.controller = vi21.ServerVirtualInterfaceController()

    def test_get_virtual_interfaces_list(self):
        req = fakes.HTTPRequest.blank('', version=self.wsgi_api_version)
        res_dict = self.controller.index(req, 'fake_uuid')
        self.assertEqual(self.expected_response, res_dict)

    def test_vif_instance_not_found(self):
        self.mox.StubOutWithMock(compute_api.API, 'get')
        fake_context = context.RequestContext('fake', 'fake')
        fake_req = FakeRequest(fake_context)
        fake_req.api_version_request = api_version_request.APIVersionRequest(
                                        self.wsgi_api_version)
        compute_api.API.get(fake_context, 'fake_uuid',
                            expected_attrs=None,
                            want_objects=True).AndRaise(
            exception.InstanceNotFound(instance_id='instance-0000'))

        self.mox.ReplayAll()
        self.assertRaises(
            webob.exc.HTTPNotFound,
            self.controller.index,
            fake_req, 'fake_uuid')

    def test_list_vifs_neutron_notimplemented(self):
        """Tests that a 400 is returned when using neutron as the backend"""
        # unset the get_vifs_by_instance stub from setUp
        self.mox.UnsetStubs()
        self.flags(use_neutron=True)
        # reset the controller to use the neutron network API
        self._set_controller()
        self.stub_out('nova.compute.api.API.get', compute_api_get)
        req = fakes.HTTPRequest.blank('', version=self.wsgi_api_version)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, req, FAKE_UUID)


class ServerVirtualInterfaceTestV20(ServerVirtualInterfaceTestV21):

    def _set_controller(self):
        self.controller = vi20.ServerVirtualInterfaceController()


class ServerVirtualInterfaceTestV212(ServerVirtualInterfaceTestV21):
    wsgi_api_version = '2.12'

    expected_response = {
        'virtual_interfaces': [
            {'id': '00000000-0000-0000-0000-00000000000000000',
                'mac_address': '00-00-00-00-00-00',
                'net_id': '22222222-2222-2222-2222-22222222222222222'},
            {'id': '11111111-1111-1111-1111-11111111111111111',
                'mac_address': '11-11-11-11-11-11',
                'net_id': '33333333-3333-3333-3333-33333333333333333'}]}


class ServerVirtualInterfaceEnforcementV21(test.NoDBTestCase):

    def setUp(self):
        super(ServerVirtualInterfaceEnforcementV21, self).setUp()
        self.controller = vi21.ServerVirtualInterfaceController()
        self.req = fakes.HTTPRequest.blank('')

    def test_index_virtual_interfaces_policy_failed(self):
        rule_name = "os_compute_api:os-virtual-interfaces"
        self.policy.set_rules({rule_name: "project:non_fake"})
        exc = self.assertRaises(
            exception.PolicyNotAuthorized,
            self.controller.index, self.req, fakes.FAKE_UUID)
        self.assertEqual(
            "Policy doesn't allow %s to be performed." % rule_name,
            exc.format_message())
