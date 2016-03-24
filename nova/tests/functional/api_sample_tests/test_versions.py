# Copyright 2012 Nebula, Inc.
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

from nova.tests.functional.api_sample_tests import api_sample_base


class VersionsSampleJsonTest(api_sample_base.ApiSampleTestBaseV21):
    sample_dir = 'versions'
    scenarios = [('', {'_test': ''})]

    def test_versions_get(self):
        response = self._do_get('', strip_version=True)
        subs = self._get_regexes()
        self._verify_response('versions-get-resp', subs, response, 200)

    def test_versions_get_v2(self):
        response = self._do_get('/v2', strip_version=True)
        subs = self._get_regexes()
        self._verify_response('v2-version-get-resp', subs, response, 200)

    def test_versions_get_v21(self):
        response = self._do_get('/v2.1', strip_version=True)
        subs = self._get_regexes()
        self._verify_response('v21-version-get-resp', subs, response, 200)
