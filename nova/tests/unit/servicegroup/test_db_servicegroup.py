# Copyright 2012 IBM Corp.
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

import datetime
import mock

from nova import objects
from nova import servicegroup
from nova import test


class DBServiceGroupTestCase(test.NoDBTestCase):

    def setUp(self):
        super(DBServiceGroupTestCase, self).setUp()
        self.down_time = 15
        self.flags(service_down_time=self.down_time,
                   servicegroup_driver='db')
        self.servicegroup_api = servicegroup.API()

    @mock.patch('oslo_utils.timeutils.utcnow')
    def test_is_up(self, now_mock):
        service_ref = {
            'host': 'fake-host',
            'topic': 'compute',
        }
        fts_func = datetime.datetime.fromtimestamp
        fake_now = 1000

        # Up (equal)
        now_mock.return_value = fts_func(fake_now)
        service_ref['last_seen_up'] = fts_func(fake_now - self.down_time)
        service_ref['updated_at'] = fts_func(fake_now - self.down_time)
        service_ref['created_at'] = fts_func(fake_now - self.down_time)

        result = self.servicegroup_api.service_is_up(service_ref)
        self.assertTrue(result)

        # Up
        service_ref['last_seen_up'] = fts_func(fake_now - self.down_time + 1)
        service_ref['updated_at'] = fts_func(fake_now - self.down_time + 1)
        service_ref['created_at'] = fts_func(fake_now - self.down_time + 1)
        result = self.servicegroup_api.service_is_up(service_ref)
        self.assertTrue(result)

        # Down
        service_ref['last_seen_up'] = fts_func(fake_now - self.down_time - 3)
        service_ref['updated_at'] = fts_func(fake_now - self.down_time - 3)
        service_ref['created_at'] = fts_func(fake_now - self.down_time - 3)
        result = self.servicegroup_api.service_is_up(service_ref)
        self.assertFalse(result)

        # "last_seen_up" says down, "updated_at" says up.
        # This can happen if we do a service disable/enable while it's down.
        service_ref['updated_at'] = fts_func(fake_now - self.down_time + 1)
        result = self.servicegroup_api.service_is_up(service_ref)
        self.assertFalse(result)

    def test_join(self):
        service = mock.MagicMock(report_interval=1)

        self.servicegroup_api.join('fake-host', 'fake-topic', service)
        fn = self.servicegroup_api._driver._report_state
        service.tg.add_timer.assert_called_once_with(1, fn, 5, service)

    @mock.patch.object(objects.Service, 'save')
    def test_report_state(self, upd_mock):
        service_ref = objects.Service(host='fake-host', topic='compute',
                                      report_count=10)
        service = mock.MagicMock(model_disconnected=False,
                                 service_ref=service_ref)
        fn = self.servicegroup_api._driver._report_state
        fn(service)
        upd_mock.assert_called_once_with()
        self.assertEqual(11, service_ref.report_count)
