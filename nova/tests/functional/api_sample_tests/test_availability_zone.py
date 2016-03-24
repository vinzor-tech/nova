# Copyright 2013 IBM Corp.
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

import nova.conf
from nova.tests.functional.api_sample_tests import test_servers

CONF = nova.conf.CONF
CONF.import_opt('osapi_compute_extension',
                'nova.api.openstack.compute.legacy_v2.extensions')


class AvailabilityZoneJsonTest(test_servers.ServersSampleBase):
    ADMIN_API = True
    extension_name = "os-availability-zone"

    def _get_flags(self):
        f = super(AvailabilityZoneJsonTest, self)._get_flags()
        f['osapi_compute_extension'] = CONF.osapi_compute_extension[:]
        f['osapi_compute_extension'].append(
            'nova.api.openstack.compute.contrib.availability_zone.'
            'Availability_zone')
        return f

    def test_availability_zone_list(self):
        response = self._do_get('os-availability-zone')
        self._verify_response('availability-zone-list-resp', {}, response, 200)

    def test_availability_zone_detail(self):
        response = self._do_get('os-availability-zone/detail')
        self._verify_response('availability-zone-detail-resp', {}, response,
                              200)

    def test_availability_zone_post(self):
        self._post_server()
